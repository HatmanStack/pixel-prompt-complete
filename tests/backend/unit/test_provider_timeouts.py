"""Tests that no provider can outlive the dispatch budget.

handle_generate's timeout cannot cancel a future that has already started:
the provider call is blocking I/O inside a worker thread. So the budget is
only meaningful if every provider bounds its own call below it. Otherwise the
request is abandoned, the user is told the model failed, and the provider
generates and bills for the image anyway.

Nova was unbounded until this change, using botocore's defaults of 60s
connect plus 60s read with legacy retries.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFRONT_DOMAIN", "test.cloudfront.net")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


@pytest.fixture(autouse=True)
def _synchronous_dispatch(monkeypatch):
    """This module exercises the dispatch loop, not the transport.

    GENERATE_ASYNC defaults true, which makes /generate answer 202 before any
    provider runs. Patched on the config module rather than set in os.environ
    because config reads the variable once at import, and this module is not
    the first to import it. The asynchronous path is covered in
    tests/backend/unit/test_generate_async_dispatch.py.
    """
    import config

    monkeypatch.setattr(config, "generate_async", False)



def test_bedrock_client_has_bounded_timeouts():
    import utils.clients as c

    c._bedrock_clients.clear()
    cfg = c.get_bedrock_client().meta.config
    assert cfg.read_timeout is not None, "Nova would use botocore's 60s default"
    assert cfg.connect_timeout is not None


def test_nova_worst_case_fits_inside_the_dispatch_budget():
    """Every attempt maxing out connect AND read, plus retry backoff, must fit.

    The earlier version of this test computed read_timeout * attempts, which
    is not the bound botocore enforces: connect_timeout and read_timeout
    apply to separate phases, so one attempt can take their sum. That test
    passed against a client whose real worst case was 120s on a 70s budget --
    it encoded the same wrong model as the code it was checking.
    """
    import config
    import utils.clients as c

    c._bedrock_clients.clear()
    cfg = c.get_bedrock_client().meta.config
    attempts = cfg.retries["total_max_attempts"]
    worst_case = attempts * (cfg.connect_timeout + cfg.read_timeout)
    worst_case += c.BEDROCK_BACKOFF_ALLOWANCE
    assert worst_case <= config.generate_dispatch_budget_seconds, (
        f"Nova can run {worst_case}s against a "
        f"{config.generate_dispatch_budget_seconds}s budget"
    )


def test_read_timeout_tracks_the_budget():
    """The bound is derived, so tuning API_CLIENT_TIMEOUT cannot silently break it."""
    import utils.clients as c

    for budget in (30.0, 70.0, 200.0):
        assert c.bedrock_worst_case_seconds(budget) <= budget, budget


def test_read_timeout_stays_positive_on_an_absurdly_small_budget():
    """A misconfigured budget should fail fast, not produce a zero or negative timeout."""
    import utils.clients as c

    assert c.bedrock_read_timeout(1.0) >= 1


def test_retries_are_capped():
    """Unbounded retries would multiply the timeout past any budget."""
    import utils.clients as c

    c._bedrock_clients.clear()
    cfg = c.get_bedrock_client().meta.config
    assert cfg.retries["total_max_attempts"] <= 2


def test_gemini_client_passes_a_timeout():
    import utils.clients as c

    c._genai_clients.clear()
    client = c.get_genai_client("k", timeout=30.0)
    assert client is not None
    # A distinct cache entry per timeout, so an untimed client cannot be
    # returned to a caller that asked for one.
    assert ("k", 30.0) in c._genai_clients


def test_dispatch_budget_exceeds_the_client_timeout():
    """The budget must be the outer bound, not the inner one."""
    import config

    assert config.generate_dispatch_budget_seconds > config.api_client_timeout


def test_bedrock_client_is_cached_per_region():
    import utils.clients as c

    c._bedrock_clients.clear()
    a = c.get_bedrock_client("us-west-2")
    b = c.get_bedrock_client("us-west-2")
    assert a is b
    assert c.get_bedrock_client("eu-west-1") is not a


def test_running_calls_are_reported_when_models_were_also_skipped():
    """The regression this counter was written for, and originally missed.

    Skipped models are merged into ``results`` before dispatch, so counting
    the still-running futures as ``len(futures) - cancelled - len(results)``
    subtracts models that were never dispatched. With three capped models and
    one real call still burning money it yields -2, the log never fires, and
    the billed-but-abandoned work stays invisible -- the exact case the log
    exists to surface.
    """
    import json
    from unittest.mock import MagicMock, patch

    from users.quota import QuotaResult
    from users.tier import TierContext

    def _model(name, provider):
        m = MagicMock()
        m.name = name
        m.provider = provider
        return m

    models = [
        _model("gemini", "google_gemini"),
        _model("nova", "bedrock_nova"),
        _model("openai", "openai"),
        _model("firefly", "adobe_firefly"),
    ]

    # Already running: cancel() fails, and it is neither cancelled nor done.
    running = MagicMock()
    running.cancel.return_value = False
    running.cancelled.return_value = False
    running.done.return_value = False

    with (
        patch("config.auth_enabled", True),
        patch("lambda_function._guest_service", MagicMock()),
        patch("lambda_function._user_repo") as mock_repo,
        patch("lambda_function.resolve_tier") as mock_tier,
        patch("lambda_function.enforce_quota") as mock_quota,
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function.get_enabled_models", return_value=models),
        patch("lambda_function._model_counter_service") as mock_counter,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function._executor") as mock_exec,
        patch("lambda_function.as_completed", side_effect=TimeoutError()),
        patch("lambda_function.StructuredLogger.error") as mock_error,
    ):
        mock_repo.get_model_runtime_config.return_value = None
        mock_tier.return_value = TierContext(
            tier="paid", user_id="u1", email=None,
            is_authenticated=True, guest_token_id=None, issue_guest_cookie=False,
        )
        mock_quota.return_value = QuotaResult(allowed=True, reason=None, reset_at=0)
        mock_cf.check_prompt.return_value = False
        mock_sm.create_session.return_value = "s1"
        # Three models capped, only nova dispatched.
        mock_counter.consume_model_slot.side_effect = lambda name, now: name == "nova"
        mock_exec.submit.return_value = running

        from lambda_function import handle_generate

        handle_generate(
            {
                "body": json.dumps({"prompt": "a cat"}),
                "requestContext": {"http": {"sourceIp": "127.0.0.1"}},
                "headers": {},
            },
            "corr-timeout",
        )

    budget_logs = [
        c for c in mock_error.call_args_list if "still running" in str(c.args[0])
    ]
    assert budget_logs, "abandoned provider call was not reported"
    assert budget_logs[0].kwargs["stillRunning"] == 1


# ---------------------------------------------------------------------------
# The invariant, for every provider rather than only Bedrock.
#
# config.py states that every provider must bound its own call below the
# dispatch budget. Until Task 1 that was asserted for Bedrock alone, which is
# how outpaint_firefly came to chain four sequential 60s calls against a 70s
# budget without a single test noticing.
# ---------------------------------------------------------------------------


def test_sync_budget_fits_inside_the_gateway_ceiling():
    """/iterate, /outpaint and /enhance are answered inside the HTTP request.

    Their whole chain has to clear the 29s gateway ceiling, not the 70s
    dispatch budget the asynchronous worker enjoys.
    """
    import config

    assert config.sync_dispatch_budget_seconds < config.gateway_integration_timeout_seconds
    assert config.sync_dispatch_budget_seconds > 0


def test_enhance_timeout_cannot_exceed_the_sync_budget():
    """A 30s enhance timeout inside a 29s ceiling cannot succeed at its limit."""
    import importlib

    import config

    previous = os.environ.get("ENHANCE_TIMEOUT")
    os.environ["ENHANCE_TIMEOUT"] = "300"
    try:
        reloaded = importlib.reload(config)
        assert reloaded.enhance_timeout == reloaded.sync_dispatch_budget_seconds
    finally:
        if previous is None:
            os.environ.pop("ENHANCE_TIMEOUT", None)
        else:
            os.environ["ENHANCE_TIMEOUT"] = previous
        importlib.reload(config)


def test_enhance_timeout_below_the_budget_is_left_alone():
    """The clamp is a ceiling, not an override: a shorter value must survive."""
    import importlib

    import config

    previous = os.environ.get("ENHANCE_TIMEOUT")
    os.environ["ENHANCE_TIMEOUT"] = "5"
    try:
        reloaded = importlib.reload(config)
        assert reloaded.enhance_timeout == 5.0
    finally:
        if previous is None:
            os.environ.pop("ENHANCE_TIMEOUT", None)
        else:
            os.environ["ENHANCE_TIMEOUT"] = previous
        importlib.reload(config)


def test_bedrock_worst_case_fits_the_synchronous_budget_too():
    """Nova is reachable from /iterate and /outpaint, which have 25s, not 70s."""
    import config
    import utils.clients as c

    budget = config.sync_dispatch_budget_seconds
    assert c.bedrock_worst_case_seconds(budget) <= budget


def test_firefly_worst_case_fits_inside_the_budget():
    """outpaint_firefly chains token -> upload -> expand -> download.

    Three of those four calls used a hardcoded _API_TIMEOUT = 60, so the real
    worst case was ~190s against a 70s budget.
    """
    import utils.clients as c

    for budget in (30.0, 70.0, 200.0):
        assert c.firefly_worst_case_seconds(budget) <= budget, budget


def test_firefly_call_timeout_stays_positive_on_an_absurdly_small_budget():
    """A misconfigured budget should not produce a zero or negative timeout.

    requests treats timeout=0 as an immediate failure and a negative timeout
    raises, so either would turn a tuning mistake into a total provider outage.
    """
    import utils.clients as c

    assert c.firefly_call_timeout(1.0) >= 1


def test_openai_worst_case_fits_inside_the_budget():
    """The SDK call and the image download are sequential, so both count."""
    import utils.clients as c

    for budget in (30.0, 70.0, 200.0):
        assert c.openai_worst_case_seconds(budget) <= budget, budget


def test_gemini_worst_case_fits_inside_the_budget():
    import utils.clients as c

    for budget in (30.0, 70.0, 200.0):
        assert c.gemini_worst_case_seconds(budget) <= budget, budget


def test_every_configured_provider_has_a_bound_and_respects_it():
    """The invariant config.py states, checked for all four providers at once.

    Table-driven over config.MODELS rather than a hardcoded list: a fifth
    provider added without an entry in PROVIDER_WORST_CASE fails here, which
    is the only mechanism that stops the next unbounded provider shipping.
    """
    import config
    import utils.clients as c

    providers = {m.provider for m in config.MODELS.values()}
    missing = providers - set(c.PROVIDER_WORST_CASE)
    assert not missing, f"providers with no worst-case bound: {sorted(missing)}"

    for provider in sorted(providers):
        worst_case = c.PROVIDER_WORST_CASE[provider]
        for budget in (
            config.sync_dispatch_budget_seconds,
            config.api_client_timeout,
            config.generate_dispatch_budget_seconds,
        ):
            assert worst_case(budget) <= budget, (provider, budget, worst_case(budget))


def _png_bytes(width: int = 1024, height: int = 1024) -> bytes:
    """A real PNG, because outpaint_firefly reads the source dimensions."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _firefly_config(budget=None):
    cfg = {
        "provider": "adobe_firefly",
        "id": "firefly-image-5",
        "api_key": "",
        "client_id": "cid",
        "client_secret": "secret",
    }
    if budget is not None:
        cfg["timeout"] = budget
    return cfg


def _mock_the_firefly_chain(m, generate_url):
    import models.providers.firefly as firefly_mod

    m.post(firefly_mod._TOKEN_URL, json={"access_token": "t"})
    m.post(firefly_mod._STORAGE_URL, json={"images": [{"id": "upload-1"}]})
    m.post(generate_url, json={"outputs": [{"image": {"url": "https://img.example/x.png"}}]})
    m.get("https://img.example/x.png", content=b"\x89PNG-not-really")


def _reset_firefly_token():
    import models.providers.firefly as firefly_mod

    firefly_mod._cached_token = None
    firefly_mod._cached_token_expiry = 0.0


def test_iterate_firefly_bounds_its_whole_chain_by_the_budget_it_was_given():
    """Four sequential HTTP calls, and their sum has to fit the budget.

    Asserting on the timeout argument is asserting on the contract here: a
    blocking call that cannot be cancelled costs exactly its timeout in the
    worst case, so the timeout IS the bound.
    """
    import base64

    import requests_mock

    import config
    import models.providers.firefly as firefly_mod
    import utils.clients as c

    _reset_firefly_token()
    budget = config.sync_dispatch_budget_seconds
    expected = c.firefly_call_timeout(budget)

    with requests_mock.Mocker() as m:
        _mock_the_firefly_chain(m, firefly_mod._GENERATE_URL)
        result = firefly_mod.iterate_firefly(
            _firefly_config(budget),
            base64.b64encode(b"source").decode(),
            "a cat",
            [],
        )

    assert result["status"] == "success", result
    timeouts = [r.timeout for r in m.request_history]
    assert len(timeouts) == c.FIREFLY_SEQUENTIAL_CALLS
    assert timeouts[0] == c.FIREFLY_TOKEN_TIMEOUT
    assert timeouts[1:] == [expected] * (c.FIREFLY_SEQUENTIAL_CALLS - 1)
    assert sum(timeouts) <= budget


def test_outpaint_firefly_bounds_its_whole_chain_by_the_budget_it_was_given():
    """The path the finding is actually about: ~190s against a 70s budget."""
    import requests_mock

    import config
    import models.providers.firefly as firefly_mod
    import utils.clients as c

    _reset_firefly_token()
    budget = config.sync_dispatch_budget_seconds
    expected = c.firefly_call_timeout(budget)

    with requests_mock.Mocker() as m:
        _mock_the_firefly_chain(m, firefly_mod._EXPAND_URL)
        result = firefly_mod.outpaint_firefly(
            _firefly_config(budget),
            _png_bytes(),
            "16:9",
            "a cat",
        )

    assert result["status"] == "success", result
    timeouts = [r.timeout for r in m.request_history]
    assert len(timeouts) == c.FIREFLY_SEQUENTIAL_CALLS
    assert sum(timeouts) <= budget
    # Anchor the declared worst case to the timeouts actually issued. Without
    # this, firefly_worst_case_seconds is checked only against its own
    # arithmetic: drop the token call from the sum and every "fits the budget"
    # assertion still passes while the real chain overruns by 10s. Verified by
    # mutation -- removing FIREFLY_TOKEN_TIMEOUT from the worst case is caught
    # here and nowhere else.
    assert sum(timeouts) == c.firefly_worst_case_seconds(budget)


def test_firefly_falls_back_to_the_generate_budget_when_none_is_supplied():
    """/generate runs in the worker with 900s and no gateway; it keeps the
    larger budget rather than inheriting the synchronous one."""
    import requests_mock

    import config
    import models.providers.firefly as firefly_mod
    import utils.clients as c

    _reset_firefly_token()
    expected = c.firefly_call_timeout(config.api_client_timeout)

    with requests_mock.Mocker() as m:
        _mock_the_firefly_chain(m, firefly_mod._GENERATE_URL)
        result = firefly_mod.handle_firefly(_firefly_config(), "a cat", {})

    assert result["status"] == "success", result
    timeouts = [r.timeout for r in m.request_history]
    # handle_firefly is token -> generate -> download: three calls, not four.
    assert timeouts[1:] == [expected, expected]
    assert expected > c.firefly_call_timeout(config.sync_dispatch_budget_seconds)


def _stub_model_config():
    import config

    return config.ModelConfig(
        name="gemini",
        provider="google_gemini",
        enabled=True,
        api_key="k",
        model_id="gemini-3.1-flash-image-preview",
        display_name="Gemini",
    )


def _recorder(seen):
    def _handler(model_config, *_args, **_kwargs):
        seen.append(model_config)
        return {"status": "success", "image": "aGk=", "model": "m", "provider": "google_gemini"}

    return _handler


def test_refinement_hands_the_provider_the_synchronous_budget():
    """/iterate is answered inside the HTTP request, so 60s cannot be its bound."""
    import json
    from unittest.mock import MagicMock, patch

    import config
    from users.quota import QuotaResult

    seen: list[dict] = []
    session = {
        "sessionId": "s1",
        "visibility": "public",
        "models": {
            "gemini": {
                "iterationCount": 1,
                "iterations": [{"index": 0, "status": "completed", "imageKey": "k.png"}],
            }
        },
    }

    with (
        patch("lambda_function._spend_ceiling_exceeded", return_value=(False, "")),
        patch("lambda_function.enforce_quota") as mock_quota,
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function.get_model", return_value=_stub_model_config()),
        patch("lambda_function._model_runtime_disabled", return_value=False),
        patch("lambda_function._model_counter_service") as mock_counter,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function.image_storage") as mock_storage,
        patch("lambda_function.context_manager"),
        patch("lambda_function.get_iterate_handler", return_value=_recorder(seen)),
        patch("lambda_function._handle_successful_result", return_value={
            "image_key": "k", "image_url": "u"
        }),
        patch("lambda_function._cost_meter"),
        patch("lambda_function.emit_request_metric"),
        patch("lambda_function._user_repo"),
    ):
        mock_quota.return_value = QuotaResult(allowed=True, reason=None, reset_at=0)
        mock_cf.check_prompt.return_value = False
        mock_counter.consume_model_slot.return_value = True
        mock_sm.get_session.return_value = session
        mock_sm.add_iteration.return_value = 1
        mock_storage.get_image_bytes.return_value = b"png-bytes"

        from lambda_function import handle_iterate

        resp = handle_iterate(
            {
                "body": json.dumps(
                    {"sessionId": "s1", "model": "gemini", "prompt": "bluer"}
                ),
                "requestContext": {"http": {"sourceIp": "127.0.0.1"}},
                "headers": {},
            },
            "corr-sync",
        )

    assert resp["statusCode"] == 200, resp
    assert seen, "the provider handler was never reached"
    assert seen[0]["timeout"] == config.sync_dispatch_budget_seconds


def test_generation_dispatch_keeps_the_larger_asynchronous_budget():
    """After Phase 3 the dispatch runs in a worker with 900s and no gateway.

    Handing it the 25s synchronous budget would make every model fail for a
    ceiling that does not apply to it.
    """
    from unittest.mock import MagicMock, patch

    seen: list[dict] = []
    model = _stub_model_config()

    with (
        patch("lambda_function.get_enabled_models", return_value=[model]),
        patch("lambda_function.prompt_enhancer") as mock_enh,
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function.get_handler", return_value=_recorder(seen)),
        patch("lambda_function._handle_successful_result", return_value={
            "image_key": "k", "image_url": "u"
        }),
        patch("lambda_function._cost_meter"),
        patch("ops.metrics._get_cw_client"),
        patch("lambda_function._user_repo", MagicMock()),
    ):
        mock_enh.adapt_per_model.return_value = {"gemini": "a cat"}
        mock_cf.check_prompt.return_value = False
        mock_sm.add_iteration.return_value = 0

        from lambda_function import run_generation

        run_generation(
            {
                "sessionId": "s1",
                "prompt": "a cat",
                "modelNames": ["gemini"],
                "skipped": {},
                "visibility": "public",
                "tier": "anon",
                "userId": "anon",
                "correlationId": "corr-async",
            }
        )

    assert seen, "the provider handler was never reached"
    assert "timeout" not in seen[0], (
        "the generate dispatch must not inherit the synchronous budget"
    )


def test_openai_client_is_built_with_the_derived_timeout_and_no_hidden_retries():
    """The multiplier openai_worst_case_seconds assumes, checked at the source.

    The SDK defaults max_retries to 2, which makes the configured timeout a
    per-attempt bound rather than a total one. If that default came back, the
    worst case would be three times what OPENAI_MAX_ATTEMPTS declares and
    every budget assertion would still pass, because they all read the same
    constant. This reads what the client was actually constructed with.
    """
    from unittest.mock import patch

    import utils.clients as c

    c._openai_clients.clear()
    budget = 70.0
    with patch("utils.clients.OpenAI") as mock_openai:
        c.get_openai_client("k", timeout=c.openai_call_timeout(budget))

    kwargs = mock_openai.call_args.kwargs
    assert kwargs["max_retries"] == c.OPENAI_MAX_ATTEMPTS - 1
    assert kwargs["timeout"] == c.openai_call_timeout(budget)
    assert (
        c.openai_worst_case_seconds(budget)
        >= c.OPENAI_MAX_ATTEMPTS * c.openai_call_timeout(budget)
    )
