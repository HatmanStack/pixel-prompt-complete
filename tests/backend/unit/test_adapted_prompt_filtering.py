"""Tests that the LLM-rewritten prompt is filtered, not just the user's.

The content filter ran at request validation, but what reaches the provider
is `adapt_per_model`'s rewrite. That left an unchecked channel between the
check and the call: whatever the model produced went straight to four image
providers unexamined.
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

CLEAN = "a serene mountain landscape"


def _event(prompt=CLEAN):
    return {
        "body": json.dumps({"prompt": prompt}),
        "requestContext": {"http": {"sourceIp": "203.0.113.5", "method": "POST"}},
        "headers": {},
    }


def _model(name, provider):
    m = MagicMock()
    m.name = name
    m.provider = provider
    return m


@pytest.fixture
def generate_stack():
    """A /generate run with controllable adaptation output."""
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
    ):
        mock_repo.get_model_runtime_config.return_value = None
        mock_quota.return_value = QuotaResult(
            allowed=True, reason=None, reset_at=0, usage={}
        )
        mock_models.return_value = [
            _model("gemini", "google_gemini"),
            _model("nova", "bedrock_nova"),
        ]
        mock_counter.consume_model_slot.return_value = True
        mock_sm.create_session.return_value = "s1"
        mock_sm.add_iteration.return_value = 0

        # Run submitted work inline. Mocking the executor outright would skip
        # generate_for_model entirely, and that is the function which actually
        # hands the adapted prompt to the provider — the thing under test.
        submitted = []

        def run_inline(fn, model_cfg):
            fut = MagicMock()
            try:
                fut.result.return_value = fn(model_cfg)
            except Exception as e:  # surfaced via the future, as the real one does
                fut.result.side_effect = e
            submitted.append(fut)
            return fut

        mock_exec.submit.side_effect = run_inline
        yield {
            "enhancer": mock_enh,
            "session": mock_sm,
            "submitted": submitted,
        }


def _run(stack):
    from lambda_function import handle_generate

    with patch("lambda_function.as_completed", side_effect=lambda f, timeout=None: list(f)):
        return handle_generate(_event(), "corr-1")


def test_blocked_rewrite_falls_back_to_the_original(generate_stack):
    """A rewrite that trips the filter must not reach the provider."""
    generate_stack["enhancer"].adapt_per_model.return_value = {
        "gemini": "an explicit nude figure",
        "nova": "a serene mountain landscape, golden hour",
    }
    _run(generate_stack)

    stored = {
        c.args[1]: c.kwargs.get("adapted_prompt")
        for c in generate_stack["session"].add_iteration.call_args_list
    }
    assert stored["gemini"] == CLEAN, "blocked rewrite was sent to the provider"


def test_one_bad_rewrite_does_not_punish_the_other_models(generate_stack):
    """Comparing models is the product; one bad rewrite must not kill the run."""
    generate_stack["enhancer"].adapt_per_model.return_value = {
        "gemini": "an explicit nude figure",
        "nova": "a serene mountain landscape, golden hour",
    }
    resp = _run(generate_stack)

    assert resp["statusCode"] == 200
    stored = {
        c.args[1]: c.kwargs.get("adapted_prompt")
        for c in generate_stack["session"].add_iteration.call_args_list
    }
    assert stored["nova"] == "a serene mountain landscape, golden hour"


def test_clean_rewrites_pass_through_untouched(generate_stack):
    """The filter must not damage the feature it is guarding."""
    adapted = {
        "gemini": "a serene mountain landscape, dramatic light",
        "nova": "a serene mountain landscape, golden hour",
    }
    generate_stack["enhancer"].adapt_per_model.return_value = dict(adapted)
    _run(generate_stack)

    stored = {
        c.args[1]: c.kwargs.get("adapted_prompt")
        for c in generate_stack["session"].add_iteration.call_args_list
    }
    assert stored == adapted


def test_unchanged_rewrite_is_not_rechecked(generate_stack):
    """When adaptation is unavailable it returns the original verbatim.

    That string was already checked at validation, so re-running the filter
    would be wasted work on every request in open-source mode.
    """
    generate_stack["enhancer"].adapt_per_model.return_value = {
        "gemini": CLEAN,
        "nova": CLEAN,
    }
    with patch("lambda_function.content_filter") as mock_cf:
        mock_cf.check_prompt.return_value = False
        _run(generate_stack)
        # Once for the user's prompt at validation; not again for identical text.
        assert mock_cf.check_prompt.call_count == 1


def test_all_rewrites_blocked_still_returns_a_result(generate_stack):
    """Every model falls back rather than the request failing."""
    generate_stack["enhancer"].adapt_per_model.return_value = {
        "gemini": "explicit nude content",
        "nova": "explicit nude content",
    }
    resp = _run(generate_stack)

    assert resp["statusCode"] == 200
    stored = {
        c.args[1]: c.kwargs.get("adapted_prompt")
        for c in generate_stack["session"].add_iteration.call_args_list
    }
    assert set(stored.values()) == {CLEAN}
