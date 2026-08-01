"""Tests for the bounded gallery index.

``GET /gallery/list`` is unauthenticated and unquota'd. Clamping the number
of folders returned bounded the per-folder fan-out but not the listing
itself: S3 returns ``CommonPrefixes`` ascending, so the newest N are on the
LAST page and every public request paged the whole ``sessions/`` prefix to
reach them. The cost of a public GET grew with every retained session.

The assertions that matter here count *operations*, not results. A test that
only checks the returned page is satisfied by the unbounded implementation
too, which is exactly how this survived a suite that already had gallery
pagination coverage.
"""

from __future__ import annotations

import json
import os

import boto3
import pytest
from moto import mock_aws

from gallery.repository import GalleryIndexRepository, created_at_from_gallery_id

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

TABLE_NAME = "test-gallery-index"


@pytest.fixture
def dynamodb_table():
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "promptOwner", "AttributeType": "S"},
                {"AttributeName": "createdAt", "AttributeType": "N"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "PromptHistoryIndex",
                    "KeySchema": [
                        {"AttributeName": "promptOwner", "KeyType": "HASH"},
                        {"AttributeName": "createdAt", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.meta.client.get_waiter("table_exists").wait(TableName=TABLE_NAME)
        yield dynamodb, TABLE_NAME


@pytest.fixture
def repo(dynamodb_table):
    dynamodb, table_name = dynamodb_table
    return GalleryIndexRepository(table_name, dynamodb_resource=dynamodb)


def _folder(i: int) -> str:
    """A gallery folder name, one second apart, oldest at i=0."""
    h, remainder = divmod(i, 3600)
    m, s = divmod(remainder, 60)
    return f"2026-01-01-{h:02d}-{m:02d}-{s:02d}"


# ---- id <-> timestamp ----


def test_created_at_is_derived_from_the_folder_name():
    """Index order must equal the lexicographic order of the S3 paths.

    Deriving the sort key from the clock at write time instead would reorder
    a page the moment a backfill ran.
    """
    assert created_at_from_gallery_id("2026-01-01-00-00-00") == 1767225600
    # The session-id suffix disambiguates the folder, not the instant.
    assert created_at_from_gallery_id("2026-01-01-00-00-00-abcd1234") == 1767225600
    assert created_at_from_gallery_id("2026-01-01-00-00-01") == 1767225601


def test_created_at_rejects_malformed_ids():
    assert created_at_from_gallery_id("") is None
    assert created_at_from_gallery_id("not-a-timestamp") is None
    assert created_at_from_gallery_id("2026-13-45-99-99-99") is None
    assert created_at_from_gallery_id("2026-01-01") is None


def test_unparseable_folder_is_not_indexed(repo):
    """A bad name must not fail an upload the user was already billed for."""
    repo.record_gallery("definitely-not-a-gallery")
    assert repo.list_recent(limit=10) == []


# ---- the finding: work proportional to the page, not the corpus ----


def test_page_is_bounded_when_many_galleries_are_retained(repo):
    """1,200 retained galleries, one 20-entry page, bounded reads.

    The unbounded implementation reads every retained prefix before slicing.
    This asserts on the number of DynamoDB queries the read costs, so it
    fails against any implementation whose cost tracks the corpus.
    """
    for i in range(1200):
        repo.record_gallery(_folder(i))

    calls: list[dict] = []
    real_query = repo._table.query

    def counting_query(**kwargs):
        calls.append(kwargs)
        return real_query(**kwargs)

    repo._table.query = counting_query

    page = repo.list_recent(limit=20)

    assert len(page) == 20
    assert len(calls) == 1, f"a 20-entry page cost {len(calls)} queries"
    # Newest first.
    assert page[0] == _folder(1199)
    assert page[-1] == _folder(1180)


def test_cursor_pages_backwards_without_rereading(repo):
    """Continuation returns stable, non-overlapping pages."""
    for i in range(60):
        repo.record_gallery(_folder(i))

    first = repo.list_recent(limit=10)
    second = repo.list_recent(limit=10, cursor=first[-1])
    third = repo.list_recent(limit=10, cursor=second[-1])

    assert first == [_folder(i) for i in range(59, 49, -1)]
    assert second == [_folder(i) for i in range(49, 39, -1)]
    assert third == [_folder(i) for i in range(39, 29, -1)]
    assert not set(first) & set(second)
    assert not set(second) & set(third)


def test_cursor_is_exclusive(repo):
    """The folder paged from must not be re-served on the next page."""
    for i in range(5):
        repo.record_gallery(_folder(i))
    page = repo.list_recent(limit=2, cursor=_folder(4))
    assert _folder(4) not in page
    assert page == [_folder(3), _folder(2)]


def test_recording_the_same_folder_twice_is_one_entry(repo):
    """A session writes several images into one folder."""
    repo.record_gallery(_folder(0))
    repo.record_gallery(_folder(0))
    repo.record_gallery(_folder(0))
    assert repo.list_recent(limit=10) == [_folder(0)]


def test_index_entries_expire_with_the_images(repo):
    """A TTL past the 30-day S3 lifecycle would advertise dead previews."""
    repo.record_gallery(_folder(0))
    item = repo._table.get_item(Key={"userId": f"gallery#{_folder(0)}"})["Item"]
    assert int(item["ttl"]) == int(item["createdAt"]) + 30 * 86400


def test_empty_index_returns_empty(repo):
    assert repo.list_recent(limit=20) == []
    assert repo.list_recent(limit=0) == []


# ---- the handler must not scan S3 once the index answers ----


@pytest.fixture
def wired_gallery(monkeypatch):
    """lambda_function wired to moto S3 + a real gallery index."""
    import importlib

    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "promptOwner", "AttributeType": "S"},
                {"AttributeName": "createdAt", "AttributeType": "N"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "PromptHistoryIndex",
                    "KeySchema": [
                        {"AttributeName": "promptOwner", "KeyType": "HASH"},
                        {"AttributeName": "createdAt", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.meta.client.get_waiter("table_exists").wait(TableName=TABLE_NAME)

        import lambda_function

        importlib.reload(lambda_function)
        from utils.storage import ImageStorage

        lambda_function.image_storage = ImageStorage(s3, "test-bucket", "https://cdn.example.com")
        lambda_function._gallery_index = GalleryIndexRepository(
            TABLE_NAME, dynamodb_resource=dynamodb
        )
        yield lambda_function, s3


def _seed_gallery_objects(s3, folders):
    for folder in folders:
        s3.put_object(
            Bucket="test-bucket",
            Key=f"sessions/{folder}/gemini-20260101000000.png",
            Body=b"\x89PNG",
        )


def _gallery_request(limit=20, cursor=None):
    params = {"limit": str(limit)}
    if cursor:
        params["cursor"] = cursor
    return {
        "rawPath": "/gallery/list",
        "requestContext": {"http": {"method": "GET", "sourceIp": "1.2.3.4"}},
        "headers": {},
        "queryStringParameters": params,
    }


def test_handler_does_not_scan_the_sessions_prefix_when_indexed(wired_gallery):
    """The finding, end to end.

    A public request must not page every retained prefix. The only S3 LISTs
    left are the per-folder image listings for the page actually returned.
    """
    lambda_function, s3 = wired_gallery
    folders = [_folder(i) for i in range(40)]
    _seed_gallery_objects(s3, folders)
    for folder in folders:
        lambda_function._gallery_index.record_gallery(folder)

    listed_prefixes: list[str] = []
    real_list = lambda_function.image_storage.s3.list_objects_v2

    def counting_list(**kwargs):
        listed_prefixes.append(kwargs.get("Prefix", ""))
        return real_list(**kwargs)

    lambda_function.image_storage.s3.list_objects_v2 = counting_list

    resp = lambda_function.lambda_handler(_gallery_request(limit=5), None)
    body = json.loads(resp["body"])

    assert resp["statusCode"] == 200
    assert len(body["galleries"]) == 5
    assert [g["id"] for g in body["galleries"]] == [_folder(i) for i in range(39, 34, -1)]
    # Every LIST is scoped to one returned folder. A bare "sessions/" here is
    # the whole-corpus scan this change removes.
    assert "sessions/" not in listed_prefixes
    assert len(listed_prefixes) == 5


def test_handler_falls_back_to_s3_for_unindexed_folders(wired_gallery):
    """Folders written before the index existed must still list.

    Without this an existing deployment's gallery goes blank on deploy.
    """
    lambda_function, s3 = wired_gallery
    _seed_gallery_objects(s3, [_folder(0), _folder(1)])

    resp = lambda_function.lambda_handler(_gallery_request(limit=20), None)
    body = json.loads(resp["body"])

    assert resp["statusCode"] == 200
    assert [g["id"] for g in body["galleries"]] == [_folder(1), _folder(0)]


def test_handler_paginates_through_the_index(wired_gallery):
    lambda_function, s3 = wired_gallery
    folders = [_folder(i) for i in range(12)]
    _seed_gallery_objects(s3, folders)
    for folder in folders:
        lambda_function._gallery_index.record_gallery(folder)

    first = json.loads(lambda_function.lambda_handler(_gallery_request(limit=5), None)["body"])
    assert [g["id"] for g in first["galleries"]] == [_folder(i) for i in range(11, 6, -1)]
    assert first["nextCursor"] == _folder(7)

    second = json.loads(
        lambda_function.lambda_handler(_gallery_request(limit=5, cursor=first["nextCursor"]), None)[
            "body"
        ]
    )
    assert [g["id"] for g in second["galleries"]] == [_folder(i) for i in range(6, 1, -1)]

    last = json.loads(
        lambda_function.lambda_handler(
            _gallery_request(limit=5, cursor=second["nextCursor"]), None
        )["body"]
    )
    assert [g["id"] for g in last["galleries"]] == [_folder(1), _folder(0)]
    assert "nextCursor" not in last


def test_index_write_failure_does_not_fail_the_generation(wired_gallery):
    """The index is a read optimisation, not a system of record."""
    lambda_function, s3 = wired_gallery

    def boom(gallery_id):
        raise RuntimeError("dynamo unavailable")

    lambda_function._gallery_index.record_gallery = boom
    # Must not raise.
    lambda_function._index_public_gallery("sessions/2026-01-01-00-00-00-abcd1234/gemini.png")


def test_only_public_uploads_are_indexed(wired_gallery):
    """A paid user's private image has no gallery folder to advertise."""
    lambda_function, s3 = wired_gallery
    lambda_function._index_public_gallery("private/some-session-id/gemini-iter0.png")
    assert lambda_function._gallery_index.list_recent(limit=10) == []

    lambda_function._index_public_gallery("sessions/2026-01-01-00-00-00-abcd1234/gemini.png")
    assert lambda_function._gallery_index.list_recent(limit=10) == ["2026-01-01-00-00-00-abcd1234"]
