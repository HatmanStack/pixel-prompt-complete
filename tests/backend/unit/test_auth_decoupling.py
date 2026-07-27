"""Tests that cost control no longer rides on the auth flag.

AUTH_ENABLED used to mean three unrelated things at once: resolve identity,
enforce quota, and enforce per-model cost caps. "I have no Cognito" and "I
want no spend limits" are unrelated statements, but one flag asserted both —
so an open deployment was necessarily an unlimited one.

These pin the separation: auth still gates identity, and nothing else.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _synchronous_dispatch(monkeypatch):
    """This module exercises the dispatch loop, not the transport.

    GENERATE_ASYNC defaults true, and /generate now returns 503 when the
    worker Invoke does not land instead of silently running the dispatch
    inline -- inline runs a ~70s budget behind a 29s gateway timeout, so the
    caller gets a 504 and never learns the sessionId. The Invoke never lands
    under test (AWS_LAMBDA_FUNCTION_NAME is unset), so these tests pin the
    synchronous path they were written for. Patched on the config module
    rather than os.environ because config reads the variable once at import.
    The asynchronous path is covered in test_generate_async_dispatch.py.
    """
    import config

    monkeypatch.setattr(config, "generate_async", False)


os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFRONT_DOMAIN", "test.cloudfront.net")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


def _event():
    return {
        "body": json.dumps({"prompt": "a cat"}),
        "requestContext": {"http": {"sourceIp": "203.0.113.7", "method": "POST"}},
        "headers": {},
    }


def _model(name, provider):
    m = MagicMock()
    m.name = name
    m.provider = provider
    return m


@pytest.fixture
def auth_off_stack():
    """A fully mocked /generate stack with AUTH_ENABLED=false."""
    from users.quota import QuotaResult

    with (
        patch("config.auth_enabled", False),
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function.get_enabled_models") as mock_models,
        patch("lambda_function._model_counter_service") as mock_counter,
        patch("lambda_function._user_repo") as mock_repo,
        patch("lambda_function.enforce_quota") as mock_quota,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function._executor") as mock_exec,
        patch("lambda_function._cost_meter") as mock_meter,
    ):
        mock_cf.check_prompt.return_value = False
        mock_models.return_value = [_model("gemini", "google_gemini")]
        mock_counter.consume_model_slot.return_value = True
        mock_repo.get_model_runtime_config.return_value = None
        mock_quota.return_value = QuotaResult(
            allowed=True, reason=None, reset_at=0, usage={}
        )
        mock_sm.create_session.return_value = "s1"
        future = MagicMock()
        future.result.return_value = ("gemini", {"status": "completed", "duration": 1.0})
        mock_exec.submit.return_value = future
        yield {
            "counter": mock_counter,
            "quota": mock_quota,
            "meter": mock_meter,
            # The exact future submit() returned: handle_generate looks the
            # future up in its own dict, so a different mock would miss.
            "future": future,
        }


def test_quota_is_enforced_with_auth_off(auth_off_stack):
    """Quota answers 'how much', which does not depend on knowing 'who'."""
    from lambda_function import handle_generate

    with patch("lambda_function.as_completed", return_value=[auth_off_stack["future"]]):
        handle_generate(_event(), "corr-1")
    auth_off_stack["quota"].assert_called()


def test_per_model_caps_are_enforced_with_auth_off(auth_off_stack):
    """The provider bills us whether or not the caller logged in."""
    from lambda_function import handle_generate

    with patch("lambda_function.as_completed", return_value=[auth_off_stack["future"]]):
        handle_generate(_event(), "corr-1")
    auth_off_stack["counter"].consume_model_slot.assert_called()


def test_spend_is_metered_with_auth_off(auth_off_stack):
    from lambda_function import handle_generate

    with patch("lambda_function.as_completed", return_value=[auth_off_stack["future"]]):
        handle_generate(_event(), "corr-1")
    auth_off_stack["meter"].record_models.assert_called()


def test_anon_quota_denial_is_honoured(auth_off_stack):
    """An over-limit anonymous caller is refused, not waved through."""
    from users.quota import QuotaResult

    auth_off_stack["quota"].return_value = QuotaResult(
        allowed=False, reason="anon_generate", reset_at=999, usage={}
    )
    from lambda_function import handle_generate

    resp = handle_generate(_event(), "corr-1")
    assert resp["statusCode"] == 429


def test_identity_endpoints_still_require_auth():
    """Auth legitimately gates identity — that separation is kept."""
    import lambda_function

    with patch("config.auth_enabled", False):
        for handler in (lambda_function.handle_me, lambda_function.handle_prompts_history):
            resp = handler({"requestContext": {"http": {"method": "GET"}}}, "c")
            assert resp["statusCode"] == 501


def test_anon_tier_is_never_paid():
    """The specific defect: anonymous callers were granted the paid tier."""
    from users.tier import anon_tier

    ctx = anon_tier(_event())
    assert ctx.tier == "anon"
    assert ctx.tier != "paid"
    assert ctx.is_authenticated is False


def test_anon_identity_is_stable_per_ip():
    """Metering needs the same caller to land in the same bucket."""
    from users.tier import anon_tier

    a = anon_tier(_event())
    b = anon_tier(_event())
    assert a.user_id == b.user_id

    other = anon_tier(
        {
            "body": "{}",
            "requestContext": {"http": {"sourceIp": "198.51.100.1", "method": "POST"}},
            "headers": {},
        }
    )
    assert other.user_id != a.user_id


def test_quota_fails_open_for_every_tier():
    """Fail-open applies uniformly, not just to anon.

    The anon path had its own try/except while guest, free and paid
    propagated to the top-level handler and 500'd — so a store outage broke
    the service for exactly the users paying for it.
    """
    import lambda_function
    from users.tier import TierContext

    for tier in ("anon", "guest", "free", "paid"):
        ctx = TierContext(
            tier=tier,
            user_id=f"{tier}#x",
            email=None,
            is_authenticated=tier in ("free", "paid"),
            guest_token_id=None,
            issue_guest_cookie=False,
            ip_hash="x",
        )
        with patch(
            "lambda_function.enforce_quota", side_effect=RuntimeError("dynamo down")
        ):
            result = lambda_function._enforce_quota_safe(ctx, "generate", 0)
        assert result.allowed is True, f"{tier} did not fail open"


def test_quota_denial_still_denies():
    """Fail-open must not swallow a legitimate denial."""
    import lambda_function
    from users.quota import QuotaResult
    from users.tier import TierContext

    ctx = TierContext(
        tier="free",
        user_id="u1",
        email=None,
        is_authenticated=True,
        guest_token_id=None,
        issue_guest_cookie=False,
    )
    denied = QuotaResult(allowed=False, reason="free_generate", reset_at=1, usage={})
    with patch("lambda_function.enforce_quota", return_value=denied):
        assert lambda_function._enforce_quota_safe(ctx, "generate", 0).allowed is False
