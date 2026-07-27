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
"""

from __future__ import annotations

import json
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


def test_the_worker_branch_runs_the_dispatch(stack):
    """lambda_handler routes a generate_worker event before any HTTP parsing."""
    import lambda_function

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

    result = lambda_function.lambda_handler(payload, None)

    assert result == {"statusCode": 200}
    stack["get_handler"].assert_called_once()
    stack["session"].add_iteration.assert_called_once_with(
        "s1", "gemini", "a cat", adapted_prompt="a cat"
    )


def test_the_worker_branch_does_not_raise_into_the_runtime(stack):
    """The per-model failures are already recorded on the session.

    Letting the exception escape turns a diagnosable session into an
    unexplained invocation error with a retry the platform chooses for us.
    """
    import lambda_function

    stack["session"].add_iteration.side_effect = RuntimeError("s3 down")

    result = lambda_function.lambda_handler(
        {
            "source": "generate_worker",
            "sessionId": "s1",
            "prompt": "a cat",
            "modelNames": ["gemini"],
            "skipped": {},
            "visibility": "public",
            "tier": None,
            "userId": None,
            "correlationId": None,
        },
        None,
    )

    assert result["statusCode"] in (200, 500)


def test_the_worker_meters_the_spend(stack):
    """The charge follows the provider call, not the HTTP response."""
    import lambda_function

    lambda_function.lambda_handler(
        {
            "source": "generate_worker",
            "sessionId": "s1",
            "prompt": "a cat",
            "modelNames": ["gemini"],
            "skipped": {},
            "visibility": "public",
            "tier": "free",
            "userId": "u1",
            "correlationId": None,
        },
        None,
    )

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
