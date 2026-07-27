"""A 429 a real handler can return must carry a usable Retry-After header.

What these tests prove: the quota rejections `/generate`, `/iterate` and
`/outpaint` actually return derive `Retry-After` from the window reset the
quota layer reports, and `response()` mirrors it onto the wire alongside the
`retryAfter` body field. The headline test drives a genuine 429 through
`lambda_handler` against moto DynamoDB with the real `UserRepository` and the
real `enforce_quota` — nothing supplies a retry interval to it, so it fails if
the call site stops computing one.

What they cannot prove: that a browser can read the header. That depends on the
deployed API Gateway's `CorsConfiguration`, which overrides the integration's
CORS headers; `test_expose_headers_is_declared_on_the_gateway` reads the
template for that half, and it is a file, not an account.
"""

from __future__ import annotations

import importlib
import json
import os
import pathlib
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import boto3
import pytest
import yaml
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

import lambda_function
from users.quota import QuotaResult
from utils import error_responses

TEMPLATE = pathlib.Path(__file__).resolve().parents[3] / "backend" / "template.yaml"


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


@pytest.fixture
def auth_env(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "secret")
    monkeypatch.setenv("FREE_REFINE_LIMIT", "1")
    monkeypatch.setenv("FREE_WINDOW_SECONDS", "3600")
    import config as cfg

    importlib.reload(cfg)
    import auth.guest_token as gt

    gt.reset_guest_token_service()
    yield
    for v in ("GUEST_TOKEN_SECRET", "FREE_REFINE_LIMIT", "FREE_WINDOW_SECONDS"):
        monkeypatch.delenv(v, raising=False)
    # AUTH_ENABLED has no default: reloading without it raises.
    monkeypatch.setenv("AUTH_ENABLED", "false")
    importlib.reload(cfg)
    gt.reset_guest_token_service()


@pytest.fixture
def wired(auth_env):
    """The real repository and quota layer over moto DynamoDB."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="pixel-prompt-users",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        importlib.reload(lambda_function)
        from users.repository import UserRepository

        lambda_function._user_repo = UserRepository(
            "pixel-prompt-users", dynamodb_resource=ddb
        )
        yield lambda_function


def test_a_real_quota_429_carries_a_header_derived_from_the_window(wired):
    """The headline. No test double supplies the interval — the code computes it.

    A signed-in free user with FREE_REFINE_LIMIT=1 refines twice. The second
    call is refused by the real enforce_quota against real DynamoDB state, and
    the header must equal both the body field and the seconds remaining on the
    window the quota layer reported in resetAt.
    """
    claims = {"sub": "cog-free-retry", "email": "u@x.com"}

    with (
        patch.object(wired, "session_manager") as sm,
        patch.object(wired, "image_storage") as img,
        patch.object(wired, "context_manager") as cm,
        patch.object(wired, "get_model") as gm,
        patch.object(wired, "get_model_config_dict", return_value={"id": "x"}),
        patch.object(wired, "get_iterate_handler") as gih,
    ):
        sm.get_session.return_value = {
            "models": {
                "gemini": {
                    "iterationCount": 0,
                    "iterations": [
                        {"index": 0, "status": "completed", "imageKey": "k.png"}
                    ],
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

        assert wired.lambda_handler(_ev(), None)["statusCode"] == 200
        denied = wired.lambda_handler(_ev(), None)
        observed_at = int(time.time())

    body = _body(denied)
    assert denied["statusCode"] == 429
    assert body["error"] == "TIER_QUOTA_EXCEEDED"

    header = denied["headers"].get("Retry-After")
    assert header is not None, (
        "a 429 the handler actually returns carries no Retry-After"
    )
    assert header == str(body["retryAfter"])
    # Derived from the real window, not a constant: resetAt is what the quota
    # layer reported, and the interval must land on it.
    assert abs((observed_at + body["retryAfter"]) - body["resetAt"]) <= 2
    assert 0 < body["retryAfter"] <= 3600


def test_guest_ip_limit_carries_the_header():
    """The quota decision is stubbed; the interval is still the code's own.

    `_enforce_quota_safe` returns a genuine QuotaResult, which is exactly what
    the quota layer returns in production. Deleting `retry_after=` from the
    guest_ip_limit call site fails this.
    """
    now = int(time.time())
    result = QuotaResult(allowed=False, reason="guest_ip", reset_at=now + 900, usage={})

    with (
        patch.object(lambda_function, "_enforce_quota_safe", return_value=result),
        patch.object(lambda_function, "content_filter") as cf,
    ):
        cf.check_prompt.return_value = False
        resp = lambda_function.handle_generate(
            _event(body={"prompt": "a cat"}), "corr-1"
        )

    body = _body(resp)
    assert resp["statusCode"] == 429
    assert body["error"] == "GUEST_IP_LIMIT"
    assert resp["headers"]["Retry-After"] == str(body["retryAfter"])
    assert 890 <= body["retryAfter"] <= 900


def test_guest_global_limit_carries_the_header():
    now = int(time.time())
    result = QuotaResult(
        allowed=False, reason="guest_global", reset_at=now + 60, usage={}
    )

    with (
        patch.object(lambda_function, "_enforce_quota_safe", return_value=result),
        patch.object(lambda_function, "content_filter") as cf,
    ):
        cf.check_prompt.return_value = False
        resp = lambda_function.handle_generate(
            _event(body={"prompt": "a cat"}), "corr-1"
        )

    body = _body(resp)
    assert resp["statusCode"] == 429
    assert body["error"] == "GUEST_GLOBAL_LIMIT"
    assert resp["headers"]["Retry-After"] == str(body["retryAfter"])


def test_an_unknown_reset_instant_emits_no_header():
    """Better no header than an invented interval a client would obey."""
    result = QuotaResult(allowed=False, reason="guest_ip", reset_at=0, usage={})

    with (
        patch.object(lambda_function, "_enforce_quota_safe", return_value=result),
        patch.object(lambda_function, "content_filter") as cf,
    ):
        cf.check_prompt.return_value = False
        resp = lambda_function.handle_generate(
            _event(body={"prompt": "a cat"}), "corr-1"
        )

    assert resp["statusCode"] == 429
    assert "Retry-After" not in resp["headers"]
    assert "retryAfter" not in _body(resp)


def test_spend_ceiling_503_carries_seconds_to_utc_midnight():
    """The one factory that computed a value before this phase, on its real path."""
    with (
        patch.object(lambda_function, "_daily_spend_exceeded", return_value=True),
        patch.object(lambda_function, "content_filter") as cf,
    ):
        cf.check_prompt.return_value = False
        resp = lambda_function.handle_generate(
            _event(body={"prompt": "a cat"}), "corr-1"
        )

    body = _body(resp)
    assert resp["statusCode"] == 503
    assert body["error"] == "DAILY_SPEND_CEILING"
    assert resp["headers"]["Retry-After"] == str(body["retryAfter"])

    now = datetime.now(timezone.utc)
    seconds_to_midnight = 86400 - (now.hour * 3600 + now.minute * 60 + now.second)
    assert abs(body["retryAfter"] - seconds_to_midnight) <= 2


def test_success_response_has_no_retry_after_header():
    resp = lambda_function.response(200, {"ok": True})

    assert "Retry-After" not in resp["headers"]


def test_non_positive_retry_after_produces_no_header():
    for value in (0, -1):
        resp = lambda_function.response(429, {"error": "X", "retryAfter": value})

        assert "Retry-After" not in resp["headers"], (
            f"retryAfter={value} is not an interval a client can wait for"
        )


def test_non_integer_retry_after_produces_no_header():
    """A string or bool would render as a header value no client can parse."""
    for value in ("soon", True, None, 12.5):
        resp = lambda_function.response(429, {"error": "X", "retryAfter": value})

        assert "Retry-After" not in resp["headers"], (
            f"retryAfter={value!r} leaked a header"
        )


def test_the_integration_response_declares_expose_headers():
    """Half of the cross-origin story: what the Lambda itself returns."""
    body = error_responses.tier_quota_exceeded("free", 0, retry_after=60)
    resp = lambda_function.response(429, body)

    assert "Retry-After" in resp["headers"]["Access-Control-Expose-Headers"]


def test_expose_headers_is_declared_on_the_gateway():
    """The other half, and the one that decides what the browser sees.

    ADR-A9 records that an HttpApi with a CorsConfiguration overrides the
    integration's CORS headers, so the Expose-Headers the Lambda sets does not
    survive the deployed path on its own. Retry-After is not CORS-safelisted,
    so without this declaration `response.headers.get('Retry-After')` in the
    client is null cross-origin and the whole feature is unreadable.
    """

    class _Loader(yaml.SafeLoader):
        pass

    for tag in (
        "!Ref",
        "!Sub",
        "!GetAtt",
        "!Equals",
        "!If",
        "!Not",
        "!Join",
        "!Select",
        "!Split",
        "!FindInMap",
        "!Condition",
        "!And",
        "!Or",
        "!ImportValue",
        "!Base64",
    ):
        _Loader.add_constructor(tag, lambda loader, node: None)

    doc = yaml.load(TEMPLATE.read_text(), Loader=_Loader)
    cors = doc["Resources"]["HttpApi"]["Properties"]["CorsConfiguration"]

    assert "Retry-After" in cors.get("ExposeHeaders", []), (
        "the gateway does not expose Retry-After, so a browser cannot read the "
        "header the Lambda sets"
    )
