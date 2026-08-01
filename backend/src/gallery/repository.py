"""DynamoDB index of public gallery folders, newest first.

``GET /gallery/list`` is unauthenticated and unquota'd, so the work one
request can ask for has to be bounded by the request itself. Clamping the
number of folders *returned* did not do that: S3 hands ``CommonPrefixes``
back in ascending order, so the newest N sit on the LAST page and finding
them meant paging the entire ``sessions/`` prefix on every call. The cost of
a public GET therefore grew with every session the service had ever
retained, which is the amplification this index removes.

The index rides the **existing** ``PromptHistoryIndex`` GSI rather than
adding one. That index is keyed ``(promptOwner, createdAt)`` and is a
generic newest-first feed index; ``promptOwner`` is a historical name, not a
constraint on what may partition it. Reusing it keeps this a data change
rather than a table update, and a query against a single partition key with
``Limit`` set is work proportional to the page, not to the corpus.

``createdAt`` is **derived from the folder name**, not from the clock at
write time. Gallery folders are named ``YYYY-MM-DD-HH-MM-SS[-<8 chars of
session id>]``, so parsing the name gives an ordering identical to the
lexicographic one the S3 path produced — no page reorders itself when the
index is populated alongside existing folders — and makes a cursor fully
reconstructible from a gallery id, which is what keeps the public cursor
contract a gallery id instead of an opaque blob.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import boto3

# Partition key for the gallery feed on the shared PromptHistoryIndex GSI.
FEED_KEY = "GLOBAL#GALLERY"

# Item key prefix on the table itself. Also listed in
# ``UserRepository._NON_USER_PREFIXES`` so the admin user scan skips these.
ITEM_PREFIX = "gallery#"

# Matches the 30-day S3 lifecycle on session objects. An index entry that
# outlived its images would advertise a gallery whose every preview 404s.
_TTL_SECONDS = 30 * 86400

# A query returns at most 1MB per page. These items are a few hundred bytes,
# so one page covers any allowed limit many times over; the loop exists so a
# short page cannot silently truncate a caller's page, and the cap keeps that
# loop bounded rather than trading one unbounded scan for another.
_MAX_QUERY_PAGES = 3


def created_at_from_gallery_id(gallery_id: str) -> int | None:
    """Epoch seconds encoded in a gallery folder name, or None if malformed.

    Only the leading ``YYYY-MM-DD-HH-MM-SS`` is read; the optional session-id
    suffix that disambiguates two sessions starting in the same second is not
    part of the instant.
    """
    if not gallery_id or len(gallery_id) < 19:
        return None
    try:
        parsed = datetime.strptime(gallery_id[:19], "%Y-%m-%d-%H-%M-%S")
    except ValueError:
        return None
    return int(parsed.replace(tzinfo=timezone.utc).timestamp())


class GalleryIndexRepository:
    """Newest-first index of public gallery folders."""

    def __init__(self, table_name: str, dynamodb_resource: Any | None = None) -> None:
        self.table_name = table_name
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self._table = self._dynamodb.Table(table_name)

    def record_gallery(self, gallery_id: str) -> None:
        """Index one public gallery folder.

        Idempotent: the table key is the folder itself, so the several images
        a session writes into one folder collapse onto a single item instead
        of accumulating duplicates the reader would have to de-duplicate.

        Silently ignores a folder name it cannot parse. The name is built by
        ``ImageStorage.upload_image`` rather than supplied by a caller, so an
        unparseable one is a bug on our side, and failing an upload the user
        has already been billed for is the wrong way to report it.
        """
        created_at = created_at_from_gallery_id(gallery_id)
        if created_at is None:
            return
        self._table.put_item(
            Item={
                "userId": f"{ITEM_PREFIX}{gallery_id}",
                "promptOwner": FEED_KEY,
                "createdAt": created_at,
                "galleryId": gallery_id,
                "ttl": created_at + _TTL_SECONDS,
            }
        )

    def list_recent(self, limit: int, cursor: str | None = None) -> list[str]:
        """Return at most ``limit`` gallery ids, newest first.

        ``cursor`` is a gallery id from a previous page; folders strictly
        older than it are returned. Its index position is derived from the id
        itself, so no server-side cursor state is kept.
        """
        if limit <= 0:
            return []

        kwargs: dict[str, Any] = {
            "IndexName": "PromptHistoryIndex",
            "KeyConditionExpression": "promptOwner = :po",
            "ExpressionAttributeValues": {":po": FEED_KEY},
            "ScanIndexForward": False,
            "Limit": limit,
        }
        if cursor:
            created_at = created_at_from_gallery_id(cursor)
            if created_at is not None:
                kwargs["ExclusiveStartKey"] = {
                    "promptOwner": FEED_KEY,
                    "createdAt": created_at,
                    "userId": f"{ITEM_PREFIX}{cursor}",
                }

        found: list[str] = []
        for _ in range(_MAX_QUERY_PAGES):
            response = self._table.query(**kwargs)
            for item in response.get("Items", []):
                gallery_id = item.get("galleryId")
                if gallery_id:
                    found.append(str(gallery_id))
                    if len(found) >= limit:
                        return found
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key
            kwargs["Limit"] = limit - len(found)
        return found
