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

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFRONT_DOMAIN", "test.cloudfront.net")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


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
