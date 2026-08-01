"""
E2E test fixtures providing real S3-backed components via MiniStack.

All external model API calls are stubbed with fake image generators,
but all S3 state management runs against real MiniStack S3.

GENERATE_ASYNC is forced false for the same reason: MiniStack provides S3 only,
so there is no Lambda service to self-invoke. With the production default,
/generate would answer 202 and hand the provider dispatch to an invocation that
never happens, and every workflow assertion downstream would read an empty
session. Synchronous mode runs the identical dispatch in-process, so the suite
still exercises the whole path -- it is the transport that is stubbed out, not
the work.
"""

import os
import uuid
from unittest.mock import patch

import boto3
import pytest
import requests

# Set before anything imports config: config reads the variable once, at import,
# and nothing above this line pulls it in.
os.environ["GENERATE_ASYNC"] = "false"

# ── MiniStack connectivity check ──────────────────────────────────────

MINISTACK_ENDPOINT = os.environ.get("MINISTACK_ENDPOINT", "http://localhost:4566")


def _ministack_available() -> bool:
    try:
        resp = requests.get(f"{MINISTACK_ENDPOINT}/_ministack/health", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


skip_no_ministack = pytest.mark.skipif(
    not _ministack_available(),
    reason="MiniStack not running",
)

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def ministack_s3():
    """Create a real S3 client pointing at MiniStack with a fresh bucket."""
    s3 = boto3.client(
        "s3",
        endpoint_url=MINISTACK_ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    bucket = f"e2e-test-{uuid.uuid4().hex[:8]}"
    s3.create_bucket(Bucket=bucket)
    yield s3, bucket

    # Cleanup: delete all objects then the bucket
    try:
        resp = s3.list_objects_v2(Bucket=bucket)
        for obj in resp.get("Contents", []):
            s3.delete_object(Bucket=bucket, Key=obj["Key"])
        s3.delete_bucket(Bucket=bucket)
    except Exception:
        pass


def _ministack_has_dynamodb() -> bool:
    """Whether this MiniStack build serves DynamoDB.

    The `light` edition serves S3 only, and its banner advertises services it
    does not implement -- CreateTable answers 400 `Unsupported service`. The
    gallery listing became index-backed when the unbounded `sessions/` walk
    was removed, so without DynamoDB that one workflow cannot be exercised
    here and says so, rather than appearing to pass.
    """
    try:
        resp = requests.get(f"{MINISTACK_ENDPOINT}/_ministack/health", timeout=2)
        return "dynamodb" in (resp.json().get("services") or {})
    except Exception:
        return False


requires_dynamodb = pytest.mark.skipif(
    not _ministack_has_dynamodb(),
    reason="MiniStack light serves S3 only; the gallery index needs DynamoDB",
)


@pytest.fixture
def ministack_dynamodb():
    """The users table plus the GSI the gallery index reads, when available.

    Yields ``(None, None)`` on a build without DynamoDB so the rest of the
    suite -- which is about the S3-backed session workflow -- still runs.
    """
    if not _ministack_has_dynamodb():
        yield None, None
        return

    dynamodb = boto3.resource(
        "dynamodb",
        endpoint_url=MINISTACK_ENDPOINT,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    table_name = f"e2e-users-{uuid.uuid4().hex[:8]}"
    table = dynamodb.create_table(
        TableName=table_name,
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
    yield dynamodb, table_name

    try:
        table.delete()
    except Exception:
        pass


def _fake_generate(config, prompt, params):
    """Fake image generation handler returning a deterministic base64 stub."""
    return {"status": "success", "image": "ZmFrZWltYWdl"}  # base64("fakeimage")


def _fake_iterate(config, source_image, prompt, context):
    """Fake iteration handler."""
    return {"status": "success", "image": "aXRlcmF0ZWQ="}  # base64("iterated")


def _fake_outpaint(config, source_image, preset, prompt):
    """Fake outpaint handler."""
    return {"status": "success", "image": "b3V0cGFpbnRlZA=="}  # base64("outpainted")


@pytest.fixture
def e2e_handler(ministack_s3, ministack_dynamodb):
    """
    Construct real S3-backed components against MiniStack, patch them into
    lambda_function module singletons, and yield the lambda_handler.

    Only model API handler functions are stubbed with fakes.
    """
    s3, bucket = ministack_s3
    dynamodb, table_name = ministack_dynamodb

    from gallery.repository import GalleryIndexRepository
    from jobs.manager import SessionManager
    from models.context import ContextManager
    from utils.content_filter import ContentFilter
    from utils.storage import ImageStorage

    sm = SessionManager(s3, bucket)
    cm = ContextManager(s3, bucket)
    storage = ImageStorage(s3, bucket, "test.cloudfront.net")
    cf = ContentFilter()

    patches = {
        # Redundant with the GENERATE_ASYNC env var above, deliberately: the
        # env var only takes effect if nothing imported config first, and this
        # does not care about import order.
        "config.generate_async": False,
        "lambda_function.s3_client": s3,
        "lambda_function.session_manager": sm,
        "lambda_function.context_manager": cm,
        "lambda_function.image_storage": storage,
        "lambda_function.content_filter": cf,
        "lambda_function.get_handler": lambda provider: _fake_generate,
        "lambda_function.get_iterate_handler": lambda provider: _fake_iterate,
        "lambda_function.get_outpaint_handler": lambda provider: _fake_outpaint,
    }

    if table_name is not None:
        # Per-container cache of the backfill marker; each test gets a fresh
        # table, so a carried-over True would skip the backfill.
        patches["lambda_function._gallery_index"] = GalleryIndexRepository(
            table_name, dynamodb_resource=dynamodb
        )
        patches["lambda_function._gallery_backfilled"] = False

    patchers = []
    for target, value in patches.items():
        p = patch(target, value)
        p.start()
        patchers.append(p)

    from lambda_function import lambda_handler

    yield lambda_handler, sm, cm, storage, None

    for p in patchers:
        p.stop()
