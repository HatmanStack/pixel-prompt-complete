"""Tests for tier/quota wiring into lambda_function._parse_and_validate_request."""

from __future__ import annotations

import importlib
import json
import os
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


@pytest.fixture
def auth_env(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "secret")
    monkeypatch.setenv("GUEST_GENERATE_LIMIT", "1")
    monkeypatch.setenv("GUEST_GLOBAL_LIMIT", "5")
    monkeypatch.setenv("FREE_GENERATE_LIMIT", "1")
    monkeypatch.setenv("FREE_REFINE_LIMIT", "2")
    import config as cfg
    importlib.reload(cfg)
    import auth.guest_token as gt
    gt.reset_guest_token_service()
    yield
    for v in (
        "AUTH_ENABLED",
        "GUEST_TOKEN_SECRET",
        "GUEST_GENERATE_LIMIT",
        "GUEST_GLOBAL_LIMIT",
        "FREE_GENERATE_LIMIT",
        "FREE_REFINE_LIMIT",
    ):
        monkeypatch.delenv(v, raising=False)
    importlib.reload(cfg)
    gt.reset_guest_token_service()


@pytest.fixture
def wired(auth_env):
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="pixel-prompt-users",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        import lambda_function
        importlib.reload(lambda_function)
        # Repoint _user_repo at moto resource
        from users.repository import UserRepository
        lambda_function._user_repo = UserRepository(
            "pixel-prompt-users", dynamodb_resource=ddb
        )
        yield lambda_function


def _event(method="POST", path="/generate", body=None, headers=None):
    e = {
        "rawPath": path,
        "requestContext": {"http": {"method": method, "sourceIp": "1.2.3.4"}},
        "headers": headers or {},
    }
    if body is not None:
        e["body"] = json.dumps(body)
    return e


def _body(resp):
    return json.loads(resp["body"])


def test_guest_generate_ok_and_cookie(wired):
    """Guest hits /generate once: response ok + Set-Cookie present."""
    fake_model = MagicMock(provider="google_gemini")
    fake_model.name = "gemini"

    with patch.object(wired, "get_enabled_models", return_value=[fake_model]), \
         patch.object(wired, "session_manager") as sm, \
         patch.object(wired, "_executor") as ex, \
         patch.object(wired, "get_handler") as gh, \
         patch.object(wired, "get_model_config_dict", return_value={"id": "x"}), \
         patch.object(wired, "image_storage") as img, \
         patch.object(wired, "context_manager"), \
         patch.object(wired, "as_completed") as ac:
        sm.create_session.return_value = "sess"
        sm.add_iteration.return_value = 0
        gh.return_value = lambda c, p, params: {"status": "success", "image": "b"}
        img.upload_image.return_value = "k"
        img.get_cloudfront_url.return_value = "https://cdn/k"
        fut = MagicMock()
        fut.result.return_value = (
            "gemini",
            {"status": "completed", "imageKey": "k", "imageUrl": "x", "iteration": 0, "duration": 0.1},
        )
        ex.submit.return_value = fut
        ac.return_value = iter([fut])

        resp = wired.lambda_handler(_event(body={"prompt": "hi"}), None)
    assert resp["statusCode"] == 200
    assert "cookies" in resp
    assert any("pp_guest=" in c for c in resp["cookies"])


def test_guest_iterate_blocked_402(wired):
    """Guest hits /iterate: blocked before reaching session logic."""
    resp = wired.lambda_handler(
        _event(
            path="/iterate",
            body={"sessionId": "s1", "model": "gemini", "prompt": "more"},
        ),
        None,
    )
    assert resp["statusCode"] == 402
    assert _body(resp)["error"] == "AUTH_REQUIRED"


def test_free_user_exceeds_refine_quota_429(wired):
    """Signed-in free user: 3rd refine returns 429."""
    # Simulate authenticated request via jwt claims.
    claims = {"sub": "cog-free", "email": "u@x.com"}

    # Need the session fetch to return something so the refine runs.
    with patch.object(wired, "session_manager") as sm, \
         patch.object(wired, "image_storage") as img, \
         patch.object(wired, "context_manager") as cm, \
         patch.object(wired, "get_model") as gm, \
         patch.object(wired, "get_model_config_dict", return_value={"id": "x"}), \
         patch.object(wired, "get_iterate_handler") as gih:
        sm.get_session.return_value = {
            "models": {
                "gemini": {
                    "iterationCount": 0,
                    "iterations": [{"index": 0, "status": "completed", "imageKey": "k.png"}],
                }
            }
        }
        sm.add_iteration.return_value = 1
        img.get_image_bytes.return_value = b"\x89PNG"
        img.upload_image.return_value = "k2.png"
        img.get_cloudfront_url.return_value = "u"
        cm.get_context_for_iteration.return_value = []
        gm.return_value = MagicMock(provider="google_gemini")
        gih.return_value = lambda c, s, p, ctx: {"status": "success", "image": "new"}

        def _ev():
            e = _event(
                path="/iterate",
                body={"sessionId": "s1", "model": "gemini", "prompt": "more"},
            )
            e["requestContext"]["authorizer"] = {"jwt": {"claims": claims}}
            return e

        r1 = wired.lambda_handler(_ev(), None)
        r2 = wired.lambda_handler(_ev(), None)
        r3 = wired.lambda_handler(_ev(), None)
    assert r1["statusCode"] == 200
    assert r2["statusCode"] == 200
    assert r3["statusCode"] == 429
    assert _body(r3)["error"] == "TIER_QUOTA_EXCEEDED"


def test_paid_generate_unlimited(wired):
    """Paid user hits /generate many times — no quota block."""
    claims = {"sub": "cog-paid", "email": "p@x.com"}
    wired._user_repo.get_or_create_user("cog-paid")
    wired._user_repo.set_tier("cog-paid", "paid")

    fake_model = MagicMock(provider="google_gemini")
    fake_model.name = "gemini"
    with patch.object(wired, "get_enabled_models", return_value=[fake_model]), \
         patch.object(wired, "session_manager") as sm, \
         patch.object(wired, "_executor") as ex, \
         patch.object(wired, "get_handler") as gh, \
         patch.object(wired, "get_model_config_dict", return_value={"id": "x"}), \
         patch.object(wired, "image_storage") as img, \
         patch.object(wired, "context_manager"), \
         patch.object(wired, "as_completed") as ac:
        sm.create_session.return_value = "sess"
        sm.add_iteration.return_value = 0
        gh.return_value = lambda c, p, params: {"status": "success", "image": "b"}
        img.upload_image.return_value = "k"
        img.get_cloudfront_url.return_value = "u"
        fut = MagicMock()
        fut.result.return_value = (
            "gemini",
            {"status": "completed", "imageKey": "k", "imageUrl": "u", "iteration": 0, "duration": 0.1},
        )
        ex.submit.return_value = fut

        def _ev():
            e = _event(body={"prompt": "hi"})
            e["requestContext"]["authorizer"] = {"jwt": {"claims": claims}}
            return e

        for _ in range(5):
            ac.return_value = iter([fut])
            resp = wired.lambda_handler(_ev(), None)
            assert resp["statusCode"] == 200
