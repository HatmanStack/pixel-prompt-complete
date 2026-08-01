"""Unauthenticated endpoints that cost money need a per-caller bound.

Two endpoints reach a shared, billable resource with no identity attached:

* ``POST /enhance`` calls the configured LLM. It is public, CAPTCHA-free and
  explicitly skips tier quota. A dedicated daily sub-ceiling bounds the
  *money*, but any one anonymous caller could spend the whole allocation, at
  which point every legitimate enhance request gets a 503 until reset — the
  cost guard turned into the denial-of-service amplifier it was added to
  prevent.
* ``POST /log`` writes caller-chosen records to CloudWatch at any level up to
  a 10KB body. Ingestion is billed and the log is where an incident is
  diagnosed, so an unmetered writer buys both cost and cover.

Both relied on API Gateway throttling alone, which is a global bound: it
caps everyone together and so cannot stop one caller consuming the share of
all the others. That is the gap here — one per-IP bound, applied to both.

What these tests cannot prove: that an IP is a person. It is not, and these
are abuse ceilings rather than fair-use quotas, exactly as the existing anon
and guest IP buckets are.
"""

from __future__ import annotations

import importlib
import json
import os
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

_TABLE = "pixel-prompt-users"


@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("ENHANCE_IP_LIMIT", "2")
    monkeypatch.setenv("ENHANCE_IP_WINDOW_SECONDS", "3600")
    monkeypatch.setenv("LOG_IP_LIMIT", "3")
    monkeypatch.setenv("LOG_IP_WINDOW_SECONDS", "3600")
    import config as cfg

    importlib.reload(cfg)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=_TABLE,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        import lambda_function

        importlib.reload(lambda_function)
        from users.repository import UserRepository

        lambda_function._user_repo = UserRepository(_TABLE, dynamodb_resource=ddb)
        yield lambda_function
    for v in (
        "ENHANCE_IP_LIMIT",
        "ENHANCE_IP_WINDOW_SECONDS",
        "LOG_IP_LIMIT",
        "LOG_IP_WINDOW_SECONDS",
    ):
        monkeypatch.delenv(v, raising=False)
    importlib.reload(cfg)


def _enhance_event(ip="1.2.3.4"):
    return {
        "rawPath": "/enhance",
        "requestContext": {"http": {"method": "POST", "sourceIp": ip}},
        "headers": {},
        "body": json.dumps({"prompt": "a cat"}),
    }


def _log_event(ip="1.2.3.4", message="something broke"):
    return {
        "rawPath": "/log",
        "requestContext": {"http": {"method": "POST", "sourceIp": ip}},
        "headers": {},
        "body": json.dumps({"level": "ERROR", "message": message}),
    }


# --------------------------------------------------------------------------
# /enhance
# --------------------------------------------------------------------------


def test_enhance_is_capped_per_source_ip(wired):
    """The finding: one anonymous caller must not be able to spend the day."""
    with patch.object(wired, "prompt_enhancer") as enhancer:
        enhancer.enhance_variants.return_value = ("short", "long")

        assert wired.lambda_handler(_enhance_event(), None)["statusCode"] == 200
        assert wired.lambda_handler(_enhance_event(), None)["statusCode"] == 200

        third = wired.lambda_handler(_enhance_event(), None)
        assert third["statusCode"] == 429
        assert json.loads(third["body"])["error"] == "IP_RATE_LIMIT"
        # The bound has to stop the spend, so it must precede the LLM call.
        assert enhancer.enhance_variants.call_count == 2


def test_enhance_limit_is_per_ip_not_global(wired):
    """A global cap cannot distinguish one abuser from the whole internet."""
    with patch.object(wired, "prompt_enhancer") as enhancer:
        enhancer.enhance_variants.return_value = ("short", "long")

        for _ in range(3):
            wired.lambda_handler(_enhance_event(ip="1.1.1.1"), None)

        other = wired.lambda_handler(_enhance_event(ip="2.2.2.2"), None)
        assert other["statusCode"] == 200


def test_enhance_rate_limit_carries_retry_after(wired):
    with patch.object(wired, "prompt_enhancer") as enhancer:
        enhancer.enhance_variants.return_value = ("short", "long")
        for _ in range(2):
            wired.lambda_handler(_enhance_event(), None)
        resp = wired.lambda_handler(_enhance_event(), None)

    assert resp["statusCode"] == 429
    assert json.loads(resp["body"])["retryAfter"] > 0
    assert int(resp["headers"]["Retry-After"]) > 0


def test_enhance_survives_an_unreachable_counter(wired):
    """Fail open, matching every other guard over this table.

    An unreachable counter is not evidence the caller is over limit, and
    503ing a public endpoint because DynamoDB hiccuped is a self-inflicted
    outage. The daily spend sub-ceiling still bounds the money.
    """
    with (
        patch.object(wired, "prompt_enhancer") as enhancer,
        patch.object(wired._user_repo, "increment_anon", side_effect=RuntimeError("dynamo down")),
    ):
        enhancer.enhance_variants.return_value = ("short", "long")
        for _ in range(5):
            assert wired.lambda_handler(_enhance_event(), None)["statusCode"] == 200


# --------------------------------------------------------------------------
# /log
# --------------------------------------------------------------------------


def test_log_is_capped_per_source_ip(wired):
    """The finding: CloudWatch ingestion is billed and drowns the signal."""
    with patch.object(wired, "handle_log") as log_fn:
        log_fn.return_value = {"success": True, "message": "ok"}

        for _ in range(3):
            assert wired.lambda_handler(_log_event(), None)["statusCode"] == 200

        fourth = wired.lambda_handler(_log_event(), None)
        assert fourth["statusCode"] == 429
        assert json.loads(fourth["body"])["error"] == "IP_RATE_LIMIT"
        # Rejected before the record is written, or the cap bounds nothing.
        assert log_fn.call_count == 3


def test_log_limit_is_per_ip_not_global(wired):
    with patch.object(wired, "handle_log") as log_fn:
        log_fn.return_value = {"success": True, "message": "ok"}
        for _ in range(4):
            wired.lambda_handler(_log_event(ip="1.1.1.1"), None)
        assert wired.lambda_handler(_log_event(ip="2.2.2.2"), None)["statusCode"] == 200


def test_log_survives_an_unreachable_counter(wired):
    with (
        patch.object(wired, "handle_log") as log_fn,
        patch.object(wired._user_repo, "increment_anon", side_effect=RuntimeError("dynamo down")),
    ):
        log_fn.return_value = {"success": True, "message": "ok"}
        for _ in range(5):
            assert wired.lambda_handler(_log_event(), None)["statusCode"] == 200


def test_oversized_log_body_is_still_rejected_first(wired):
    """The existing 10KB guard must not be displaced by the new one."""
    event = _log_event()
    event["body"] = "x" * (wired.MAX_LOG_BODY_SIZE + 1)
    assert wired.lambda_handler(event, None)["statusCode"] == 413


# --------------------------------------------------------------------------
# Bucket hygiene
# --------------------------------------------------------------------------


def test_rate_limit_buckets_are_not_reported_as_users(wired):
    """These rows share the users table; the admin scan must skip them."""
    with patch.object(wired, "handle_log") as log_fn:
        log_fn.return_value = {"success": True, "message": "ok"}
        wired.lambda_handler(_log_event(), None)

    users, _ = wired._user_repo.scan_users(limit=50)
    assert users == []


def test_enhance_and_log_do_not_share_a_bucket(wired):
    """Two endpoints, two budgets: logging must not exhaust enhancement."""
    with (
        patch.object(wired, "prompt_enhancer") as enhancer,
        patch.object(wired, "handle_log") as log_fn,
    ):
        enhancer.enhance_variants.return_value = ("short", "long")
        log_fn.return_value = {"success": True, "message": "ok"}

        for _ in range(3):
            wired.lambda_handler(_log_event(), None)

        assert wired.lambda_handler(_enhance_event(), None)["statusCode"] == 200
