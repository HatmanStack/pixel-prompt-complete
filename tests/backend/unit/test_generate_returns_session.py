"""Tests that /generate returns the finished session.

The client previously discarded this response, built empty placeholders, and
re-fetched the identical data by polling /status every 2s for up to five
minutes — up to 150 Lambda invocations and S3 reads per generation, for data
it had already been handed.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFRONT_DOMAIN", "test.cloudfront.net")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

FINISHED_SESSION = {
    "sessionId": "s1",
    "status": "completed",
    "prompt": "a cat",
    "createdAt": "2026-07-26T00:00:00Z",
    "updatedAt": "2026-07-26T00:00:05Z",
    "models": {
        "gemini": {
            "iterations": [
                {"status": "completed", "imageKey": "sessions/s1/gemini/0.png"}
            ]
        },
        "nova": {"iterations": [{"status": "error", "error": "boom"}]},
    },
}


def _event():
    return {
        "body": json.dumps({"prompt": "a cat"}),
        "requestContext": {"http": {"sourceIp": "203.0.113.5", "method": "POST"}},
        "headers": {},
    }


def _model(name, provider):
    m = MagicMock()
    m.name = name
    m.provider = provider
    return m


@pytest.fixture
def stack():
    from users.quota import QuotaResult

    with (
        patch("config.auth_enabled", False),
        patch("lambda_function._user_repo") as mock_repo,
        patch("lambda_function.enforce_quota") as mock_quota,
        patch("lambda_function.get_enabled_models") as mock_models,
        patch("lambda_function._model_counter_service") as mock_counter,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function._executor") as mock_exec,
        patch("lambda_function._cost_meter"),
        patch("lambda_function.prompt_enhancer") as mock_enh,
        patch("lambda_function._daily_spend_exceeded", return_value=False),
        patch("lambda_function.image_storage") as mock_storage,
    ):
        mock_repo.get_model_runtime_config.return_value = None
        mock_quota.return_value = QuotaResult(
            allowed=True, reason=None, reset_at=0, usage={}
        )
        mock_models.return_value = [_model("gemini", "google_gemini")]
        mock_counter.consume_model_slot.return_value = True
        mock_enh.adapt_per_model.return_value = {"gemini": "a cat"}
        mock_enh.is_available = False
        mock_sm.create_session.return_value = "s1"
        mock_sm.add_iteration.return_value = 0
        mock_sm.get_session.return_value = json.loads(json.dumps(FINISHED_SESSION))
        mock_storage.get_cloudfront_url.side_effect = lambda k: f"https://cdn.test/{k}"

        future = MagicMock()
        future.result.return_value = ("gemini", {"status": "completed", "duration": 1.0})
        mock_exec.submit.return_value = future
        yield {"future": future, "session": mock_sm, "storage": mock_storage}


def _run(stack):
    from lambda_function import handle_generate

    with patch("lambda_function.as_completed", return_value=[stack["future"]]):
        resp = handle_generate(_event(), "corr-1")
    return resp, json.loads(resp["body"])


def test_generate_returns_the_finished_session(stack):
    resp, body = _run(stack)
    assert resp["statusCode"] == 200
    assert "session" in body, "client would have to poll for data it was just sent"
    assert body["session"]["sessionId"] == "s1"


def test_returned_session_has_cloudfront_urls(stack):
    """Must match /status exactly, or the client renders one and not the other."""
    _, body = _run(stack)
    it = body["session"]["models"]["gemini"]["iterations"][0]
    assert it["imageUrl"] == "https://cdn.test/sessions/s1/gemini/0.png"


def test_per_model_outcomes_are_still_returned(stack):
    """`models` carries skipped/daily_cap entries that never become iterations."""
    _, body = _run(stack)
    assert "models" in body
    assert body["sessionId"] == "s1"


def test_generation_still_succeeds_if_the_session_readback_fails(stack):
    """The images exist and were paid for; a read-back failure must not lose them."""
    stack["session"].get_session.side_effect = RuntimeError("s3 down")
    resp, body = _run(stack)

    assert resp["statusCode"] == 200
    assert "session" not in body
    assert "models" in body, "client falls back to polling, but still gets a result"


def test_non_dict_session_is_not_attached(stack):
    """A malformed read-back must not reach json.dumps.

    Serialisation happens after the images are generated and outside any
    handler that could recover, so an unexpected type there would turn a
    successful, already-paid-for generation into a 500.
    """
    stack["session"].get_session.return_value = object()
    resp, body = _run(stack)

    assert resp["statusCode"] == 200
    assert "session" not in body


def test_missing_session_is_not_attached(stack):
    stack["session"].get_session.return_value = None
    resp, body = _run(stack)
    assert resp["statusCode"] == 200
    assert "session" not in body


# ---- Only terminal sessions may suppress polling ----


@pytest.mark.parametrize("status", ["pending", "in_progress"])
def test_nonterminal_session_is_not_attached(stack, status):
    """as_completed's timeout does not cancel in-flight futures.

    A model can still be running and writing results after the response is
    built. Attaching a pending session tells the client to stop polling for
    work that has not finished, and it would never see those images.
    """
    session = json.loads(json.dumps(FINISHED_SESSION))
    session["status"] = status
    stack["session"].get_session.return_value = session

    resp, body = _run(stack)
    assert resp["statusCode"] == 200
    assert "session" not in body, f"{status} session suppressed the polling fallback"
    assert "models" in body


@pytest.mark.parametrize("status", ["completed", "partial", "failed"])
def test_terminal_sessions_are_attached(stack, status):
    """All three terminal states are final — no model is still running."""
    session = json.loads(json.dumps(FINISHED_SESSION))
    session["status"] = status
    stack["session"].get_session.return_value = session

    _, body = _run(stack)
    assert body["session"]["status"] == status


def test_partial_results_are_still_returned_directly(stack):
    """"partial" means some models failed, not that work continues."""
    session = json.loads(json.dumps(FINISHED_SESSION))
    session["status"] = "partial"
    stack["session"].get_session.return_value = session

    _, body = _run(stack)
    assert "session" in body
    assert body["session"]["models"]["nova"]["iterations"][0]["status"] == "error"
