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


def test_index_entries_expire_before_the_images(repo):
    """The index must go first, not at the same instant.

    S3 deletes session objects at day 30. DynamoDB reaps expired items
    lazily -- up to ~48h late -- and an expired-but-unreaped item is still
    returned by queries, so a TTL matching the lifecycle exactly guarantees a
    window where the index advertises folders whose images are gone.
    """
    repo.record_gallery(_folder(0))
    item = repo._table.get_item(Key={"userId": f"gallery#{_folder(0)}"})["Item"]
    lifetime = int(item["ttl"]) - int(item["createdAt"])
    assert lifetime < 30 * 86400, "index entry outlives the S3 objects"
    assert lifetime == 28 * 86400


def test_empty_index_returns_empty(repo):
    assert repo.list_recent(limit=20) == []
    assert repo.list_recent(limit=0) == []


def test_an_unparseable_cursor_is_rejected_not_ignored(repo):
    """Ignoring it answers "page 7" with page 1 and a fresh cursor.

    An infinite-scroll client renders the newest galleries again below the
    older ones and never terminates.
    """
    for i in range(5):
        repo.record_gallery(_folder(i))

    with pytest.raises(ValueError):
        repo.list_recent(limit=2, cursor="not-a-gallery-id")


def test_backfill_indexes_folders_and_marks_completion(repo):
    assert repo.is_backfilled() is False
    indexed = repo.backfill([_folder(i) for i in range(5)])
    assert indexed == 5
    assert repo.is_backfilled() is True
    assert repo.list_recent(limit=10) == [_folder(i) for i in range(4, -1, -1)]


def test_backfill_skips_unparseable_names(repo):
    assert repo.backfill([_folder(0), "not-a-gallery", _folder(1)]) == 2
    assert repo.list_recent(limit=10) == [_folder(1), _folder(0)]


def test_the_backfill_marker_is_not_listed_as_a_gallery(repo):
    """It shares the gallery# prefix but carries no feed key."""
    repo.backfill([_folder(0)])
    assert repo.list_recent(limit=10) == [_folder(0)]


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
        # Per-container cache of the backfill marker; a reused module
        # would carry the previous test's answer into this one.
        lambda_function._gallery_backfilled = False
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




def _count_prefix_scans(lambda_function):
    """Record every S3 LIST prefix the handler issues."""
    listed: list[str] = []
    real_list = lambda_function.image_storage.s3.list_objects_v2

    def counting_list(**kwargs):
        listed.append(kwargs.get("Prefix", ""))
        return real_list(**kwargs)

    lambda_function.image_storage.s3.list_objects_v2 = counting_list
    return listed


def test_pre_index_folders_stay_listable_after_new_ones_arrive(wired_gallery):
    """The regression the first cut of this shipped.

    An existing deployment has folders in S3 and nothing in the index.
    Preferring the index the moment it held a single row made every one of
    those folders unreachable for the rest of its 30-day retention.
    """
    lambda_function, s3 = wired_gallery
    legacy = [_folder(i) for i in range(30)]
    _seed_gallery_objects(s3, legacy)

    # A new generation lands, indexing exactly one folder.
    newest = _folder(50)
    _seed_gallery_objects(s3, [newest])
    lambda_function._gallery_index.record_gallery(newest)

    resp = lambda_function.lambda_handler(_gallery_request(limit=50), None)
    body = json.loads(resp["body"])

    assert resp["statusCode"] == 200
    returned = {g["id"] for g in body["galleries"]}
    assert newest in returned
    assert set(legacy) <= returned, "pre-index folders disappeared from the gallery"


def test_pagination_reaches_past_the_first_page_on_a_cold_index(wired_gallery):
    """`or cursor` used to dead-end every deployment at page 1."""
    lambda_function, s3 = wired_gallery
    folders = [_folder(i) for i in range(30)]
    _seed_gallery_objects(s3, folders)

    seen: list[str] = []
    cursor = None
    for _ in range(5):
        body = json.loads(
            lambda_function.lambda_handler(_gallery_request(limit=10, cursor=cursor), None)["body"]
        )
        seen.extend(g["id"] for g in body["galleries"])
        cursor = body.get("nextCursor")
        if not cursor:
            break

    assert len(seen) == 30, f"pagination stopped after {len(seen)} of 30 folders"
    assert len(set(seen)) == 30, "pages overlapped"


def test_the_full_prefix_scan_happens_once_not_per_request(wired_gallery):
    """The backfill is the price of correctness; it must be paid once.

    A bare "sessions/" prefix is the whole-corpus walk. It is expected on the
    first request (populating the index) and never again.
    """
    lambda_function, s3 = wired_gallery
    folders = [_folder(i) for i in range(40)]
    _seed_gallery_objects(s3, folders)

    listed = _count_prefix_scans(lambda_function)

    first = lambda_function.lambda_handler(_gallery_request(limit=5), None)
    assert first["statusCode"] == 200
    assert "sessions/" in listed, "the backfill should have walked the prefix once"

    listed.clear()
    second = lambda_function.lambda_handler(_gallery_request(limit=5), None)
    body = json.loads(second["body"])

    assert second["statusCode"] == 200
    assert len(body["galleries"]) == 5
    assert [g["id"] for g in body["galleries"]] == [_folder(i) for i in range(39, 34, -1)]
    assert "sessions/" not in listed, "the corpus scan ran again on a warm index"
    # Only the per-folder image listings for the page actually returned.
    assert len(listed) == 5


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
        lambda_function.lambda_handler(
            _gallery_request(limit=5, cursor=first["nextCursor"]), None
        )["body"]
    )
    assert [g["id"] for g in second["galleries"]] == [_folder(i) for i in range(6, 1, -1)]

    last = json.loads(
        lambda_function.lambda_handler(
            _gallery_request(limit=5, cursor=second["nextCursor"]), None
        )["body"]
    )
    assert [g["id"] for g in last["galleries"]] == [_folder(1), _folder(0)]
    assert "nextCursor" not in last


def test_an_index_failure_does_not_restore_the_corpus_scan(wired_gallery):
    """Fail closed. This endpoint is unauthenticated and unquota'd.

    Falling back to listing S3 would hand the O(retained sessions) walk back
    to anyone who could make DynamoDB fail, for every request, for the
    duration of the outage -- exactly the amplification the index removes.
    """
    lambda_function, s3 = wired_gallery
    _seed_gallery_objects(s3, [_folder(i) for i in range(10)])
    lambda_function._gallery_backfilled = True

    def boom(limit, cursor=None):
        raise RuntimeError("dynamo partition")

    lambda_function._gallery_index.list_recent = boom
    listed = _count_prefix_scans(lambda_function)

    resp = lambda_function.lambda_handler(_gallery_request(limit=5), None)

    assert resp["statusCode"] == 503
    assert "sessions/" not in listed, "an index failure walked the whole bucket"


def test_an_invalid_cursor_is_a_400(wired_gallery):
    lambda_function, s3 = wired_gallery
    _seed_gallery_objects(s3, [_folder(0)])
    resp = lambda_function.lambda_handler(
        _gallery_request(limit=5, cursor="../../etc/passwd"), None
    )
    assert resp["statusCode"] == 400


def test_an_indexed_folder_whose_images_are_gone_is_dropped(wired_gallery):
    """S3 deletes on a schedule; DynamoDB reaps lazily.

    The gap between the two is guaranteed, so a folder with no images must
    not render as a blank tile.
    """
    lambda_function, s3 = wired_gallery
    _seed_gallery_objects(s3, [_folder(1)])
    # Indexed, but its objects have already been swept by the lifecycle rule.
    lambda_function._gallery_index.record_gallery(_folder(0))
    lambda_function._gallery_index.record_gallery(_folder(1))
    lambda_function._gallery_backfilled = True

    body = json.loads(lambda_function.lambda_handler(_gallery_request(limit=10), None)["body"])
    ids = [g["id"] for g in body["galleries"]]

    assert ids == [_folder(1)]
    assert all(g["imageCount"] > 0 for g in body["galleries"])


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
    assert lambda_function._gallery_index.list_recent(limit=10) == [
        "2026-01-01-00-00-00-abcd1234"
    ]


def test_concurrent_index_writes_do_not_lose_the_folder(wired_gallery):
    """run_generation fans out over four threads that all write here.

    boto3 resources are documented as not thread-safe, and every one of the
    four writes the same folder in the same instant.
    """
    import concurrent.futures

    lambda_function, s3 = wired_gallery
    key = "sessions/2026-01-01-00-00-00-abcd1234/gemini.png"

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: lambda_function._index_public_gallery(key), range(4)))

    assert lambda_function._gallery_index.list_recent(limit=10) == [
        "2026-01-01-00-00-00-abcd1234"
    ]
