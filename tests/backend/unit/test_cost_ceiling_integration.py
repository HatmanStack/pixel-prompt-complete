"""Tests for per-model cost ceiling integration in handle_generate."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch):
    """Set minimal env for lambda_function import."""
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("CLOUDFRONT_DOMAIN", "test.cloudfront.net")


def _make_event(prompt="test prompt"):
    return {
        "body": json.dumps({"prompt": prompt}),
        "requestContext": {"http": {"sourceIp": "127.0.0.1"}},
        "headers": {},
    }


def test_capped_model_skipped_in_response():
    """When one model is capped, it should appear as 'skipped' in results."""
    with (
        patch("config.auth_enabled", True),
        patch("lambda_function._guest_service", MagicMock()),
        patch("lambda_function._user_repo") as mock_user_repo,
        patch("lambda_function.resolve_tier") as mock_tier,
        patch("lambda_function.enforce_quota") as mock_quota,
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function.get_enabled_models") as mock_models,
        patch("lambda_function._model_counter_service") as mock_counter_svc,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function._executor") as mock_exec,
    ):
        from users.tier import TierContext
        from users.quota import QuotaResult

        mock_user_repo.get_model_runtime_config.return_value = None

        mock_tier.return_value = TierContext(
            tier="paid", user_id="u1", email=None,
            is_authenticated=True, guest_token_id=None, issue_guest_cookie=False,
        )
        mock_quota.return_value = QuotaResult(allowed=True, reason=None, reset_at=0)
        mock_cf.check_prompt.return_value = False

        model1 = MagicMock()
        model1.name = "gemini"
        model1.provider = "google_gemini"
        model2 = MagicMock()
        model2.name = "nova"
        model2.provider = "bedrock_nova"
        mock_models.return_value = [model1, model2]

        # gemini is capped, nova is allowed
        mock_counter_svc.check_model_allowed.side_effect = lambda name, now: name != "gemini"

        mock_sm.create_session.return_value = "session-123"

        # Simulate nova generating successfully via thread pool
        future = MagicMock()
        future.result.return_value = ("nova", {
            "status": "completed",
            "imageKey": "k1",
            "imageUrl": "http://example.com/k1",
            "iteration": 0,
            "duration": 1.0,
        })
        mock_exec.submit.return_value = future
        mock_exec.submit.side_effect = None

        # We need as_completed to yield our future
        from lambda_function import handle_generate
        with patch("lambda_function.as_completed", return_value=[future]):
            resp = handle_generate(_make_event(), "corr-1")

        body = json.loads(resp["body"])
        assert body["models"]["gemini"]["status"] == "skipped"
        assert body["models"]["gemini"]["reason"] == "daily_cap_reached"
        # nova was submitted to thread pool (not skipped)
        mock_exec.submit.assert_called_once()


def test_all_models_capped_returns_429():
    """When all models are capped, should return 429."""
    with (
        patch("config.auth_enabled", True),
        patch("lambda_function._guest_service", MagicMock()),
        patch("lambda_function._user_repo") as mock_user_repo,
        patch("lambda_function.resolve_tier") as mock_tier,
        patch("lambda_function.enforce_quota") as mock_quota,
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function.get_enabled_models") as mock_models,
        patch("lambda_function._model_counter_service") as mock_counter_svc,
    ):
        from users.tier import TierContext
        from users.quota import QuotaResult

        mock_user_repo.get_model_runtime_config.return_value = None

        mock_tier.return_value = TierContext(
            tier="paid", user_id="u1", email=None,
            is_authenticated=True, guest_token_id=None, issue_guest_cookie=False,
        )
        mock_quota.return_value = QuotaResult(allowed=True, reason=None, reset_at=0)
        mock_cf.check_prompt.return_value = False

        model1 = MagicMock()
        model1.name = "gemini"
        model2 = MagicMock()
        model2.name = "nova"
        mock_models.return_value = [model1, model2]

        # All models capped
        mock_counter_svc.check_model_allowed.return_value = False

        from lambda_function import handle_generate
        resp = handle_generate(_make_event(), "corr-1")

        assert resp["statusCode"] == 429
        body = json.loads(resp["body"])
        assert body["error"] == "MODEL_COST_CEILING"


def test_auth_disabled_skips_cost_ceiling():
    """When auth_enabled=false, no cap checks should happen."""
    with (
        patch("config.auth_enabled", False),
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function.get_enabled_models") as mock_models,
        patch("lambda_function._model_counter_service") as mock_counter_svc,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function._executor") as mock_exec,
    ):
        mock_cf.check_prompt.return_value = False

        model1 = MagicMock()
        model1.name = "gemini"
        model1.provider = "google_gemini"
        mock_models.return_value = [model1]

        mock_sm.create_session.return_value = "session-123"

        future = MagicMock()
        future.result.return_value = ("gemini", {
            "status": "completed",
            "imageKey": "k1",
            "imageUrl": "http://example.com/k1",
            "iteration": 0,
            "duration": 1.0,
        })
        mock_exec.submit.return_value = future

        from lambda_function import handle_generate
        with patch("lambda_function.as_completed", return_value=[future]):
            resp = handle_generate(_make_event(), "corr-1")

        assert resp["statusCode"] == 200
        # check_model_allowed should NOT have been called
        mock_counter_svc.check_model_allowed.assert_not_called()
