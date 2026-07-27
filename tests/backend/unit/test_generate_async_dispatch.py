"""POST /generate hands the provider dispatch to a worker invocation.

`/generate` ran a ~70s dispatch budget inside a request the API Gateway
abandons at 30s. The gateway returned 504 while the Lambda kept generating
images, writing S3, metering spend and debiting credits for a request the
caller had been told had failed (health finding H2). The request path now
validates, meters, reserves per-model slots, creates the session and
self-invokes with `InvocationType="Event"`, answering `202` immediately.

**What these tests prove:** the handler performs no provider work when
`GENERATE_ASYNC=true`, the worker payload carries what the worker needs, an
`Invoke` failure degrades to running inline rather than orphaning the session,
and `GENERATE_ASYNC=false` still produces the pre-async `200`.

**What they cannot prove:** that the deployed request completes inside 29
seconds. That is a property of real provider latency in a real account.
`DailySpendWarningAlarm` and the CloudWatch request-latency metric are the
production signal; these tests are the regression guard that stops
request-path work creeping back in.

The Lambda client is a `MagicMock` throughout. `moto`'s Lambda backend is not
used and should not be: it would test moto's dispatcher, not this code.

The "request path performs no provider work" block at the bottom asserts by
*category* -- no provider handler, no prompt enhancer, no session read-back, no
cost meter -- rather than by wall clock. A duration assertion would be flaky on
a CI runner and would say nothing about the deployed path either way. Each
category has a synchronous-mode counterpart asserting the same call *does*
happen, so the block cannot pass vacuously by mocking everything into silence.
"""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import Future
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
    "models": {"gemini": {"iterations": [{"status": "completed", "imageKey": "k"}]}},
}


class _InlineExecutor:
    """Runs a submitted callable immediately, on the calling thread.

    The dispatch loop uses a real `ThreadPoolExecutor`. Driving `moto` from
    four generation threads is the flaky pattern Phase-0 forbids: a failure is
    as likely to be moto's shared state as the code under test. Concurrency is
    not what any test in this module is about.
    """

    def submit(self, fn, *args, **kwargs):
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 - mirrors Executor.submit
            future.set_exception(exc)
        return future


def _event(prompt="a cat"):
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
def stack(monkeypatch):
    """A /generate request with every seam stubbed except the dispatch decision."""
    from users.quota import QuotaResult

    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "pixel-prompt-function")

    lambda_client = MagicMock()

    with (
        patch("config.auth_enabled", False),
        patch("lambda_function._user_repo") as mock_repo,
        patch("lambda_function.enforce_quota") as mock_quota,
        patch("lambda_function.get_enabled_models") as mock_models,
        patch("lambda_function._model_counter_service") as mock_counter,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function.context_manager"),
        patch("lambda_function._prompt_history"),
        patch("lambda_function._executor", _InlineExecutor()),
        patch("lambda_function._cost_meter") as mock_meter,
        patch("lambda_function.prompt_enhancer") as mock_enh,
        patch("lambda_function._daily_spend_exceeded", return_value=False),
        patch("lambda_function.image_storage") as mock_storage,
        patch("lambda_function.get_handler") as mock_get_handler,
        patch("lambda_function.get_model_config_dict", return_value={"id": "x"}),
        patch("lambda_function._get_lambda_client", return_value=lambda_client),
    ):
        mock_storage.is_private_key.return_value = False
        mock_storage.upload_image.return_value = "sessions/s1/gemini-0.png"
        mock_storage.get_cloudfront_url.side_effect = lambda k: f"https://cdn.test/{k}"
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
        mock_get_handler.return_value = lambda cfg, prompt, params: {
            "status": "success",
            "image": "aW1n",
        }

        yield {
            "lambda_client": lambda_client,
            "get_handler": mock_get_handler,
            "session": mock_sm,
            "enhancer": mock_enh,
            "cost_meter": mock_meter,
            "counter": mock_counter,
        }


def _run(async_mode=True, event=None):
    import lambda_function

    with patch.object(lambda_function.config, "generate_async", async_mode):
        resp = lambda_function.handle_generate(event or _event(), "corr-1")
    return resp, json.loads(resp["body"])


def _invoked_payload(lambda_client):
    """The worker payload, decoded. The contents are the contract, not the call shape."""
    kwargs = lambda_client.invoke.call_args.kwargs
    return json.loads(kwargs["Payload"].decode())


# ---- Asynchronous mode ----


def test_async_generate_returns_202(stack):
    resp, body = _run(async_mode=True)

    assert resp["statusCode"] == 202
    assert body["sessionId"] == "s1"
    assert body["prompt"] == "a cat"


def test_the_202_body_carries_no_session(stack):
    """The frontend's `else` branch builds a placeholder and starts polling.

    Attaching a session would tell GenerationPanel the work is finished before
    any provider has run.
    """
    _, body = _run(async_mode=True)

    assert "session" not in body


def test_dispatched_models_are_reported_pending(stack):
    _, body = _run(async_mode=True)

    assert body["models"] == {"gemini": {"status": "pending"}}


def test_skipped_models_keep_their_shape_in_the_202(stack):
    """The cap and admin-disable signals must survive the async switch.

    A skipped model never becomes a session iteration, so `models` is the only
    place the client can learn it was skipped and why.
    """
    stack["counter"].consume_model_slot.side_effect = lambda name, ts: name != "nova"
    with patch(
        "lambda_function.get_enabled_models",
        return_value=[
            _model("gemini", "google_gemini"),
            _model("nova", "bedrock_nova"),
        ],
    ):
        _, body = _run(async_mode=True)

    assert body["models"]["nova"] == {
        "status": "skipped",
        "reason": "daily_cap_reached",
    }
    assert body["models"]["gemini"] == {"status": "pending"}


def test_the_worker_is_invoked_as_an_event(stack):
    _run(async_mode=True)

    assert stack["lambda_client"].invoke.call_count == 1
    assert stack["lambda_client"].invoke.call_args.kwargs["InvocationType"] == "Event"


def test_the_worker_payload_carries_what_the_worker_needs(stack):
    """Asserted on the decoded payload: its contents are the contract."""
    _run(async_mode=True)
    payload = _invoked_payload(stack["lambda_client"])

    assert payload["source"] == "generate_worker"
    assert payload["sessionId"] == "s1"
    assert payload["prompt"] == "a cat"
    assert payload["modelNames"] == ["gemini"]
    assert payload["visibility"] == "public"


def test_the_worker_payload_is_json_serialisable(stack):
    """It crosses an Invoke boundary; a MagicMock or a dataclass would not survive."""
    _run(async_mode=True)
    payload = _invoked_payload(stack["lambda_client"])

    assert json.loads(json.dumps(payload)) == payload


def test_skipped_models_reach_the_worker_for_the_result_merge(stack):
    stack["counter"].consume_model_slot.side_effect = lambda name, ts: name != "nova"
    with patch(
        "lambda_function.get_enabled_models",
        return_value=[
            _model("gemini", "google_gemini"),
            _model("nova", "bedrock_nova"),
        ],
    ):
        _run(async_mode=True)

    payload = _invoked_payload(stack["lambda_client"])
    assert payload["modelNames"] == ["gemini"], "a skipped model must not be dispatched"
    assert payload["skipped"]["nova"]["reason"] == "daily_cap_reached"


def test_async_generate_calls_no_provider_handler(stack):
    """The assertion that proves the request path is now short."""
    _run(async_mode=True)

    stack["get_handler"].assert_not_called()


# ---- The inline fallback ----


def test_an_invoke_failure_falls_back_to_inline_execution(stack):
    """A deploy whose IAM grant did not land must degrade, not orphan sessions.

    Today's behaviour -- a slow request that may 504 -- is strictly better than
    a session that is created and never worked on.
    """
    stack["lambda_client"].invoke.side_effect = RuntimeError("AccessDeniedException")

    resp, body = _run(async_mode=True)

    assert resp["statusCode"] == 200
    stack["get_handler"].assert_called()
    assert body["models"]["gemini"]["status"] == "completed"


def test_an_invoke_failure_is_logged_at_error(stack):
    stack["lambda_client"].invoke.side_effect = RuntimeError("AccessDeniedException")

    with patch("lambda_function.StructuredLogger.error") as mock_error:
        _run(async_mode=True)

    assert mock_error.called, "a silent fallback hides a missing IAM grant forever"


def test_a_missing_function_name_falls_back_to_inline(monkeypatch, stack):
    """AWS_LAMBDA_FUNCTION_NAME is set by the runtime; outside Lambda it is absent.

    That is exactly when running inline is right -- `sam local`, a direct
    invocation, a test harness.
    """
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)

    resp, body = _run(async_mode=True)

    assert resp["statusCode"] == 200
    assert body["models"]["gemini"]["status"] == "completed"


# ---- Synchronous mode ----


def test_sync_mode_returns_200_with_the_pre_async_shape(stack):
    resp, body = _run(async_mode=False)

    assert resp["statusCode"] == 200
    assert body["sessionId"] == "s1"
    assert body["models"]["gemini"]["status"] == "completed"
    assert body["session"]["sessionId"] == "s1"


def test_sync_mode_invokes_nothing(stack):
    _run(async_mode=False)

    stack["lambda_client"].invoke.assert_not_called()


# ---- The worker branch ----


def _worker_event(**overrides):
    payload = {
        "source": "generate_worker",
        "sessionId": "s1",
        "prompt": "a cat",
        "modelNames": ["gemini"],
        "skipped": {},
        "visibility": "public",
        "tier": "anon",
        "userId": "anon#abc",
        "correlationId": "corr-1",
    }
    payload.update(overrides)
    return payload


def _worker_error_logs(caplog, needle):
    """The structured ERROR records the logger actually emitted, decoded.

    StructuredLogger writes a JSON string to the root logger, so this reads the
    real emitted record rather than a mock's call arguments. For a branch whose
    log line is the entire operator signal, the distinction is the whole point.
    """
    entries = []
    for record in caplog.records:
        if record.levelno != logging.ERROR:
            continue
        try:
            entry = json.loads(record.getMessage())
        except (ValueError, TypeError):
            continue
        if needle in entry.get("message", ""):
            entries.append(entry)
    return entries


def test_the_worker_branch_runs_the_dispatch(stack):
    """lambda_handler routes a generate_worker event before any HTTP parsing."""
    import lambda_function

    result = lambda_function.lambda_handler(_worker_event(), None)

    assert result == {"statusCode": 200}
    stack["get_handler"].assert_called_once()
    stack["session"].add_iteration.assert_called_once_with(
        "s1", "gemini", "a cat", adapted_prompt="a cat"
    )


# ---- The worker's failure path ----
#
# The exception has to originate ABOVE the executor for this branch to fire.
# generate_for_model wraps its own body in `except Exception`, so an
# add_iteration or provider failure is recorded per model and never propagates
# -- an earlier version of these tests set add_iteration.side_effect and never
# reached the branch at all. get_enabled_models is the first call
# run_generation makes that can escape.


def test_a_worker_failure_does_not_raise_into_the_runtime(stack):
    """Letting it escape would hand Lambda a retry that re-bills every image.

    The session already records what happened per model, so a platform retry
    buys nothing and costs a second full generation.
    """
    import lambda_function

    with patch(
        "lambda_function.get_enabled_models",
        side_effect=RuntimeError("config exploded"),
    ):
        result = lambda_function.lambda_handler(_worker_event(), None)

    assert result == {"statusCode": 200}


def test_a_worker_failure_emits_the_only_operator_signal_there_is(stack, caplog):
    """Swallowing the exception is deliberate, and it costs every other signal.

    No Lambda error metric, no statusCode to alarm on, and a session frozen at
    `pending` until the client's five-minute poll gives up. One ERROR line is
    all an operator gets, so it is asserted on the record the logger emitted.
    """
    import lambda_function

    with (
        caplog.at_level(logging.ERROR),
        patch(
            "lambda_function.get_enabled_models",
            side_effect=RuntimeError("config exploded"),
        ),
    ):
        lambda_function.lambda_handler(_worker_event(), None)

    entries = _worker_error_logs(caplog, "Generate worker failed")
    assert len(entries) == 1, "the sole operator signal for a dead worker was not emitted"


def test_the_worker_failure_log_identifies_the_session(stack, caplog):
    """Without the session id the log says a generation died, not which one."""
    import lambda_function

    with (
        caplog.at_level(logging.ERROR),
        patch(
            "lambda_function.get_enabled_models",
            side_effect=RuntimeError("config exploded"),
        ),
    ):
        lambda_function.lambda_handler(_worker_event(sessionId="sess-42"), None)

    entry = _worker_error_logs(caplog, "Generate worker failed")[0]
    assert entry["metadata"]["sessionId"] == "sess-42"
    assert entry["correlationId"] == "corr-1"


def test_the_worker_failure_log_carries_the_traceback(stack, caplog):
    """The message alone names the exception; only the traceback names the line."""
    import lambda_function

    with (
        caplog.at_level(logging.ERROR),
        patch(
            "lambda_function.get_enabled_models",
            side_effect=RuntimeError("config exploded"),
        ),
    ):
        lambda_function.lambda_handler(_worker_event(), None)

    entry = _worker_error_logs(caplog, "Generate worker failed")[0]
    tb = entry["metadata"]["traceback"]
    assert "RuntimeError" in tb
    assert "config exploded" in tb
    assert "run_generation" in tb


def test_a_healthy_worker_logs_no_failure(stack, caplog):
    """Keeps the three assertions above from passing on an always-on log line."""
    import lambda_function

    with caplog.at_level(logging.ERROR):
        lambda_function.lambda_handler(_worker_event(), None)

    assert _worker_error_logs(caplog, "Generate worker failed") == []


# ---- A model the worker container cannot resolve ----
#
# The request path reserves slots against its own get_enabled_models(); the
# worker rebuilds the configs from those names. The two can disagree only if a
# deploy changes a *_ENABLED variable while a request is in flight -- a case
# that needed an invocation boundary to be possible at all.
#
# run_generation is called directly here rather than through lambda_handler,
# because the returned results map is the observable contract and the worker
# branch discards it.


def test_one_unresolvable_model_does_not_abandon_the_others(stack):
    """This is the whole reason resolution does not go through config.get_model.

    That function raises ValueError for a model that is not enabled, so a
    single stale name would have cost the caller every other model too.
    """
    import lambda_function

    results = lambda_function.run_generation(_worker_event(modelNames=["gemini", "firefly"]))

    assert results["gemini"]["status"] == "completed"
    assert results["firefly"] == {"status": "error", "error": "Model is not enabled"}


def test_an_unresolvable_model_is_marked_failed_on_the_session(stack):
    """Leaving the column pending strands the session short of a terminal status.

    The client would then poll for five minutes and give up on a generation
    that was never going to arrive.
    """
    import lambda_function

    lambda_function.run_generation(_worker_event(modelNames=["gemini", "firefly"]))

    stack["session"].add_iteration.assert_any_call("s1", "firefly", "a cat")
    stack["session"].fail_iteration.assert_any_call("s1", "firefly", 0, "Model is not enabled")


def test_an_unresolvable_model_is_not_dispatched_to_a_provider(stack):
    """It has no config to dispatch with; the point is to fail it, not to guess.

    One handler fetched, for the one model that resolved. Guessing a config for
    the other would send a prompt to a provider the operator had disabled.
    """
    import lambda_function

    lambda_function.run_generation(_worker_event(modelNames=["gemini", "firefly"]))

    assert stack["get_handler"].call_count == 1


def test_an_unresolvable_model_is_logged_at_error(stack, caplog):
    """A silent skip would make a mid-deploy configuration split invisible."""
    import lambda_function

    with caplog.at_level(logging.ERROR):
        lambda_function.run_generation(_worker_event(modelNames=["gemini", "firefly"]))

    entries = _worker_error_logs(caplog, "not enabled in this container")
    assert len(entries) == 1
    assert entries[0]["metadata"]["model"] == "firefly"
    assert entries[0]["metadata"]["sessionId"] == "s1"


def test_a_failed_session_write_for_an_unresolvable_model_is_not_fatal(stack):
    """The dispatch must survive it: the other models are still worth running."""
    import lambda_function

    def _fail_only_firefly(session_id, model, prompt, **kwargs):
        if model == "firefly":
            raise RuntimeError("s3 down")
        return 0

    stack["session"].add_iteration.side_effect = _fail_only_firefly

    results = lambda_function.run_generation(_worker_event(modelNames=["gemini", "firefly"]))

    assert results["gemini"]["status"] == "completed"
    assert results["firefly"]["status"] == "error"


def test_every_named_model_resolving_marks_nothing_failed(stack):
    """Keeps the five above from passing against code that fails every model."""
    import lambda_function

    results = lambda_function.run_generation(_worker_event(modelNames=["gemini"]))

    assert results == {"gemini": results["gemini"]}
    assert results["gemini"]["status"] == "completed"
    stack["session"].fail_iteration.assert_not_called()


def test_the_worker_meters_the_spend(stack):
    """The charge follows the provider call, not the HTTP response."""
    import lambda_function

    lambda_function.lambda_handler(_worker_event(tier="free", userId="u1"), None)

    assert stack["cost_meter"].record_models.called
    assert stack["cost_meter"].record_models.call_args.kwargs["tier"] == "free"


def test_the_request_path_does_not_meter_when_async(stack):
    """Metering moved with the work; charging before dispatch would double-count."""
    _run(async_mode=True)

    stack["cost_meter"].record_models.assert_not_called()


# ---- The guest cookie ----


def test_a_202_still_carries_the_guest_cookie(stack):
    """The worker cannot set cookies, so the request path must."""
    import lambda_function
    from users.tier import TierContext

    guest = TierContext(
        tier="guest",
        user_id="guest#1",
        email=None,
        is_authenticated=False,
        guest_token_id="g1",
        issue_guest_cookie=True,
        new_guest_token="tok",
    )
    guest_service = MagicMock()
    guest_service.set_cookie_header.return_value = "pp_guest=tok; Path=/"

    with (
        patch("lambda_function.resolve_tier", return_value=guest),
        patch("lambda_function._guest_service", guest_service),
        patch("config.auth_enabled", True),
        patch.object(lambda_function.config, "generate_async", True),
    ):
        resp = lambda_function.handle_generate(_event(), "corr-1")

    assert resp["statusCode"] == 202
    assert resp["cookies"] == ["pp_guest=tok; Path=/"]


# ---- The request path performs no provider work ----
#
# This is the bound the phase exists to create, and an unasserted bound is a
# comment. Each assertion below has a GENERATE_ASYNC=false counterpart: if the
# stubbing ever silences a call in both modes, the counterpart fails and says
# so.


def test_no_provider_handler_factory_is_called_on_the_request_path(stack):
    import lambda_function

    with (
        patch.object(lambda_function, "get_iterate_handler") as iterate,
        patch.object(lambda_function, "get_outpaint_handler") as outpaint,
    ):
        _run(async_mode=True)

    stack["get_handler"].assert_not_called()
    iterate.assert_not_called()
    outpaint.assert_not_called()


def test_the_prompt_enhancer_is_not_called_on_the_request_path(stack):
    """adapt_per_model is a synchronous gpt-4o call; it moved into the worker."""
    _run(async_mode=True)

    stack["enhancer"].adapt_per_model.assert_not_called()


def test_the_session_is_not_read_back_on_the_request_path(stack):
    """The 202 carries no session, so there is nothing to read back.

    "At most once" rather than "never": the assertion is about the response no
    longer re-fetching what it just wrote, not about forbidding a future read
    that has a reason.
    """
    _run(async_mode=True)

    assert stack["session"].get_session.call_count <= 1


def test_the_cost_meter_is_not_called_on_the_request_path(stack):
    """The charge follows the provider call, which now happens in the worker."""
    _run(async_mode=True)

    stack["cost_meter"].record_models.assert_not_called()


# ---- The same four, in the opposite direction ----


def test_sync_mode_calls_the_provider_handler(stack):
    _run(async_mode=False)

    stack["get_handler"].assert_called()


def test_sync_mode_calls_the_prompt_enhancer(stack):
    _run(async_mode=False)

    stack["enhancer"].adapt_per_model.assert_called_once()


def test_sync_mode_reads_the_session_back(stack):
    _run(async_mode=False)

    assert stack["session"].get_session.call_count == 1


def test_sync_mode_calls_the_cost_meter(stack):
    _run(async_mode=False)

    stack["cost_meter"].record_models.assert_called_once()
