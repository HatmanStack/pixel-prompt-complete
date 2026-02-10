"""
E2E test fixtures providing real S3-backed components via LocalStack.

All external model API calls are stubbed with fake image generators,
but all S3 state management runs against real LocalStack S3.
"""

import json
import os
import uuid
from unittest.mock import patch

import boto3
import pytest
import requests

# ── LocalStack connectivity check ──────────────────────────────────────

LOCALSTACK_ENDPOINT = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")


def _localstack_available() -> bool:
    try:
        resp = requests.get(f"{LOCALSTACK_ENDPOINT}/_localstack/health", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


skip_no_localstack = pytest.mark.skipif(
    not _localstack_available(),
    reason="LocalStack not running",
)

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def localstack_s3():
    """Create a real S3 client pointing at LocalStack with a fresh bucket."""
    s3 = boto3.client(
        "s3",
        endpoint_url=LOCALSTACK_ENDPOINT,
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
def e2e_handler(localstack_s3):
    """
    Construct real S3-backed components against LocalStack, patch them into
    lambda_function module singletons, and yield the lambda_handler.

    Only model API handler functions are stubbed with fakes.
    """
    s3, bucket = localstack_s3

    from jobs.manager import SessionManager
    from models.context import ContextManager
    from utils.content_filter import ContentFilter
    from utils.rate_limit import RateLimiter
    from utils.storage import ImageStorage

    sm = SessionManager(s3, bucket)
    cm = ContextManager(s3, bucket)
    storage = ImageStorage(s3, bucket, "test.cloudfront.net")
    rl = RateLimiter(s3, bucket, global_limit=1000, ip_limit=50, ip_whitelist=[])
    cf = ContentFilter()

    patches = {
        "lambda_function.s3_client": s3,
        "lambda_function.session_manager": sm,
        "lambda_function.context_manager": cm,
        "lambda_function.image_storage": storage,
        "lambda_function.rate_limiter": rl,
        "lambda_function.content_filter": cf,
        "lambda_function.get_handler": lambda provider: _fake_generate,
        "lambda_function.get_iterate_handler": lambda provider: _fake_iterate,
        "lambda_function.get_outpaint_handler": lambda provider: _fake_outpaint,
    }

    patchers = []
    for target, value in patches.items():
        p = patch(target, value)
        p.start()
        patchers.append(p)

    from lambda_function import lambda_handler

    yield lambda_handler, sm, cm, storage, rl

    for p in patchers:
        p.stop()
