"""Tests that the cost meter is actually wired into the billable endpoints.

test_cost_meter.py proves the meter counts correctly in isolation. These prove
it is reached from the real request paths — the failure mode being a meter that
works perfectly and is never called.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("CLOUDFRONT_DOMAIN", "test.cloudfront.net")


def _make_event(prompt="test prompt"):
    return {
        "body": json.dumps({"prompt": prompt}),
        "requestContext": {"http": {"sourceIp": "127.0.0.1"}},
        "headers": {},
    }


def _tier_and_quota():
    from users.quota import QuotaResult
    from users.tier import TierContext

    return (
        TierContext(
            tier="paid",
            user_id="u1",
            email=None,
            is_authenticated=True,
            guest_token_id=None,
            issue_guest_cookie=False,
        ),
        QuotaResult(allowed=True, reason=None, reset_at=0),
    )


def _model(name, provider):
    m = MagicMock()
    m.name = name
    m.provider = provider
    return m


def test_generate_meters_dispatched_models_and_enhance():
    tier, quota = _tier_and_quota()
    with (
        patch("config.auth_enabled", True),
        patch("lambda_function._guest_service", MagicMock()),
        patch("lambda_function._user_repo") as mock_repo,
        patch("lambda_function.resolve_tier", return_value=tier),
        patch("lambda_function.enforce_quota", return_value=quota),
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function.get_enabled_models") as mock_models,
        patch("lambda_function._model_counter_service") as mock_counter,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function._executor") as mock_exec,
        patch("lambda_function._cost_meter") as mock_meter,
    ):
        mock_repo.get_model_runtime_config.return_value = None
        mock_cf.check_prompt.return_value = False
        mock_models.return_value = [
            _model("gemini", "google_gemini"),
            _model("nova", "bedrock_nova"),
        ]
        mock_counter.consume_model_slot.return_value = True
        mock_sm.create_session.return_value = "session-1"

        future = MagicMock()
        future.result.return_value = ("nova", {"status": "completed", "duration": 1.0})
        mock_exec.submit.return_value = future

        from lambda_function import handle_generate

        with patch("lambda_function.as_completed", return_value=[future]):
            handle_generate(_make_event(), "corr-1")

        mock_meter.record_models.assert_called_once()
        kwargs = mock_meter.record_models.call_args.kwargs
        assert sorted(kwargs["model_names"]) == ["gemini", "nova"]
        assert kwargs["operation"] == "generate"
        assert kwargs["tier"] == "paid"
        assert kwargs["user_id"] == "u1"


def test_generate_does_not_meter_skipped_models():
    """A model skipped by the cost ceiling never ran, so it costs nothing."""
    tier, quota = _tier_and_quota()
    with (
        patch("config.auth_enabled", True),
        patch("lambda_function._guest_service", MagicMock()),
        patch("lambda_function._user_repo") as mock_repo,
        patch("lambda_function.resolve_tier", return_value=tier),
        patch("lambda_function.enforce_quota", return_value=quota),
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function.get_enabled_models") as mock_models,
        patch("lambda_function._model_counter_service") as mock_counter,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function._executor") as mock_exec,
        patch("lambda_function._cost_meter") as mock_meter,
    ):
        mock_repo.get_model_runtime_config.return_value = None
        mock_cf.check_prompt.return_value = False
        mock_models.return_value = [
            _model("gemini", "google_gemini"),
            _model("nova", "bedrock_nova"),
        ]
        # gemini capped, nova allowed
        mock_counter.consume_model_slot.side_effect = lambda name, now: (
            name != "gemini"
        )
        mock_sm.create_session.return_value = "session-1"

        future = MagicMock()
        future.result.return_value = ("nova", {"status": "completed", "duration": 1.0})
        mock_exec.submit.return_value = future

        from lambda_function import handle_generate

        with patch("lambda_function.as_completed", return_value=[future]):
            handle_generate(_make_event(), "corr-1")

        kwargs = mock_meter.record_models.call_args.kwargs
        assert kwargs["model_names"] == ["nova"]


def test_generate_meters_models_that_errored():
    """The provider ran and bills us even when we could not return the result.

    This is the timeout path: as_completed's timeout does not cancel in-flight
    futures, so the model completes and is charged. Under-counting here is how
    a spend ceiling gets bypassed.
    """
    tier, quota = _tier_and_quota()
    with (
        patch("config.auth_enabled", True),
        patch("lambda_function._guest_service", MagicMock()),
        patch("lambda_function._user_repo") as mock_repo,
        patch("lambda_function.resolve_tier", return_value=tier),
        patch("lambda_function.enforce_quota", return_value=quota),
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function.get_enabled_models") as mock_models,
        patch("lambda_function._model_counter_service") as mock_counter,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function._executor") as mock_exec,
        patch("lambda_function._cost_meter") as mock_meter,
    ):
        mock_repo.get_model_runtime_config.return_value = None
        mock_cf.check_prompt.return_value = False
        mock_models.return_value = [_model("gemini", "google_gemini")]
        mock_counter.consume_model_slot.return_value = True
        mock_sm.create_session.return_value = "session-1"

        future = MagicMock()
        future.result.side_effect = RuntimeError("provider exploded")
        mock_exec.submit.return_value = future

        from lambda_function import handle_generate

        with patch("lambda_function.as_completed", return_value=[future]):
            handle_generate(_make_event(), "corr-1")

        kwargs = mock_meter.record_models.call_args.kwargs
        assert kwargs["model_names"] == ["gemini"]


def test_enhance_is_metered():
    """/enhance calls gpt-4o with no auth or quota — it must at least be visible."""
    with (
        patch("lambda_function.prompt_enhancer") as mock_enh,
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function._cost_meter") as mock_meter,
    ):
        mock_cf.check_prompt.return_value = False
        mock_enh.enhance_safe.return_value = "an enhanced prompt"

        from lambda_function import handle_enhance

        resp = handle_enhance(_make_event("a cat"), "corr-1")

        assert resp["statusCode"] == 200
        mock_meter.record.assert_called_once()
        costs = mock_meter.record.call_args.kwargs["costs"]
        assert "enhance" in costs
        assert costs["enhance"] > 0


def _refinement_patches(meter, preset_result=None):
    """Common mocks for the shared /iterate + /outpaint refinement path."""
    tier, quota = _tier_and_quota()
    model_cfg = _model("gemini", "google_gemini")
    handler = MagicMock(
        return_value=preset_result or {"status": "success", "image": "aGk=", "duration": 1.0}
    )
    return {
        "tier": tier,
        "quota": quota,
        "model_cfg": model_cfg,
        "handler": handler,
    }


def _run_refinement(
    endpoint,
    body,
    mock_meter_name="lambda_function._cost_meter",
    model_slot_granted=True,
):
    ctx = _refinement_patches(None)
    tier, quota = ctx["tier"], ctx["quota"]
    with (
        patch("config.auth_enabled", True),
        patch("lambda_function._guest_service", MagicMock()),
        patch("lambda_function._user_repo", MagicMock()),
        patch("lambda_function._model_counter_service") as mock_counter,
        patch("lambda_function.resolve_tier", return_value=tier),
        patch("lambda_function.enforce_quota", return_value=quota),
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function._validate_refinement_request") as mock_val,
        patch("lambda_function._load_source_image") as mock_load,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function._handle_successful_result") as mock_ok,
        patch("lambda_function.context_manager", MagicMock()),
        patch("lambda_function.get_iterate_handler", return_value=ctx["handler"]),
        patch("lambda_function.get_outpaint_handler", return_value=ctx["handler"]),
        patch(mock_meter_name) as mock_meter,
    ):
        mock_counter.consume_model_slot.return_value = model_slot_granted
        mock_cf.check_prompt.return_value = False
        mock_val.return_value = (("sess-1", "gemini", ctx["model_cfg"]), None)
        mock_load.return_value = (("base64image", 1), None)
        mock_sm.add_iteration.return_value = 1
        mock_ok.return_value = {"imageUrl": "http://x/y", "iteration": 1}

        import lambda_function

        event = {
            "body": json.dumps(body),
            "requestContext": {"http": {"sourceIp": "127.0.0.1"}},
            "headers": {},
        }
        fn = (
            lambda_function.handle_iterate
            if endpoint == "iterate"
            else lambda_function.handle_outpaint
        )
        resp = fn(event, "corr-1")
        return mock_meter, resp, ctx


def test_iterate_is_metered_as_refine():
    mock_meter, _, _ = _run_refinement(
        "iterate", {"sessionId": "sess-1", "model": "gemini", "prompt": "make it blue"}
    )
    mock_meter.record_models.assert_called_once()
    kwargs = mock_meter.record_models.call_args.kwargs
    assert kwargs["model_names"] == ["gemini"]
    assert kwargs["operation"] == "refine"
    assert kwargs["tier"] == "paid"


def test_outpaint_is_metered_as_outpaint():
    """Outpaint is priced separately so providers that charge differently show up."""
    mock_meter, _, _ = _run_refinement(
        "outpaint", {"sessionId": "sess-1", "model": "gemini", "preset": "16:9"}
    )
    mock_meter.record_models.assert_called_once()
    kwargs = mock_meter.record_models.call_args.kwargs
    assert kwargs["model_names"] == ["gemini"]
    assert kwargs["operation"] == "outpaint"


def test_refine_is_rejected_when_model_at_daily_cap():
    """B4: the per-model ceiling now covers refinement, not just /generate."""
    mock_meter, resp, ctx = _run_refinement(
        "iterate",
        {"sessionId": "sess-1", "model": "gemini", "prompt": "make it blue"},
        model_slot_granted=False,
    )
    assert resp["statusCode"] == 429
    assert json.loads(resp["body"])["error"] == "MODEL_COST_CEILING"
    # Rejected before the provider was called, so nothing was spent.
    ctx["handler"].assert_not_called()
    mock_meter.record_models.assert_not_called()


def test_outpaint_is_rejected_when_model_at_daily_cap():
    mock_meter, resp, ctx = _run_refinement(
        "outpaint",
        {"sessionId": "sess-1", "model": "gemini", "preset": "16:9"},
        model_slot_granted=False,
    )
    assert resp["statusCode"] == 429
    ctx["handler"].assert_not_called()
    mock_meter.record_models.assert_not_called()


def _generate_with_enhancer(is_available):
    """Run /generate with the prompt enhancer configured or not."""
    tier, quota = _tier_and_quota()
    with (
        patch("config.auth_enabled", True),
        patch("lambda_function._guest_service", MagicMock()),
        patch("lambda_function._user_repo") as mock_repo,
        patch("lambda_function.resolve_tier", return_value=tier),
        patch("lambda_function.enforce_quota", return_value=quota),
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function.get_enabled_models") as mock_models,
        patch("lambda_function._model_counter_service") as mock_counter,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function._executor") as mock_exec,
        patch("lambda_function._cost_meter") as mock_meter,
        patch("lambda_function.prompt_enhancer") as mock_enh,
    ):
        mock_repo.get_model_runtime_config.return_value = None
        mock_cf.check_prompt.return_value = False
        mock_models.return_value = [_model("gemini", "google_gemini")]
        mock_counter.consume_model_slot.return_value = True
        mock_sm.create_session.return_value = "session-1"
        type(mock_enh).is_available = property(lambda self: is_available)
        mock_enh.adapt_per_model.return_value = {"gemini": "adapted"}

        future = MagicMock()
        future.result.return_value = ("gemini", {"status": "completed", "duration": 1.0})
        mock_exec.submit.return_value = future

        from lambda_function import handle_generate

        with patch("lambda_function.as_completed", return_value=[future]):
            handle_generate(_make_event(), "corr-1")
        return mock_meter.record_models.call_args.kwargs


def test_enhance_billed_when_enhancer_configured():
    assert _generate_with_enhancer(True)["include_enhance"] is True


def test_enhance_not_billed_when_enhancer_unconfigured():
    """No PROMPT_MODEL_API_KEY means no LLM call, so no cost to book.

    Open-source mode ships without that key. Billing for a call that never
    happened would corrupt the cost data the meter exists to gather.
    """
    assert _generate_with_enhancer(False)["include_enhance"] is False
