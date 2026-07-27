"""The per-container circuit breaker over the quota/spend store.

Six guards plus the spend accounting all fail open on a store error and all
read one DynamoDB table, so a single partition problem opens every gate and
stops the metering at the same time. This is the bound that does not need
that table.

**No threaded tests here.** Phase-0's moto rule generalises: a test that
spawns threads to exercise the lock races itself, so a pass proves the
interleaving happened not to occur rather than that it cannot. The lock's
presence is verifiable by reading. What is worth asserting is the state
machine, and that it never fires while the store is healthy.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFRONT_DOMAIN", "test.cloudfront.net")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture(autouse=True)
def _clean_breaker():
    """Module-level state that leaks is how a suite passes for the wrong reason."""
    from ops import store_breaker

    store_breaker.reset()
    yield
    store_breaker.reset()


def _fail(n: int) -> None:
    from ops import store_breaker

    for _ in range(n):
        store_breaker.record_store_result(False)


class TestItNeverFiresWhileTheStoreIsHealthy:
    def test_a_fresh_breaker_does_not_shed(self):
        from ops import store_breaker

        assert store_breaker.should_shed() is False

    def test_a_long_run_of_successes_never_sheds(self):
        """A breaker that fires in the healthy case is worse than none."""
        import config
        from ops import store_breaker

        for _ in range(config.degraded_dispatch_budget * 10):
            store_breaker.record_store_result(True)
            assert store_breaker.should_shed() is False

    def test_a_healthy_run_consumes_no_degraded_budget(self):
        from ops import store_breaker

        for _ in range(50):
            store_breaker.record_store_result(True)
            store_breaker.should_shed()

        assert store_breaker.state()["degradedDispatches"] == 0


class TestTripping:
    def test_below_the_failure_threshold_it_does_not_shed(self):
        import config
        from ops import store_breaker

        _fail(config.store_failure_threshold - 1)
        assert store_breaker.should_shed() is False
        assert store_breaker.state()["degradedDispatches"] == 0

    def test_at_the_threshold_it_starts_spending_the_degraded_budget(self):
        import config
        from ops import store_breaker

        _fail(config.store_failure_threshold)

        assert store_breaker.should_shed() is False
        assert store_breaker.state()["degradedDispatches"] == 1

    def test_it_sheds_once_the_degraded_budget_is_spent(self):
        import config
        from ops import store_breaker

        _fail(config.store_failure_threshold)

        for _ in range(config.degraded_dispatch_budget):
            assert store_breaker.should_shed() is False

        assert store_breaker.should_shed() is True
        assert store_breaker.should_shed() is True

    def test_shedding_consumes_no_further_budget(self):
        import config
        from ops import store_breaker

        _fail(config.store_failure_threshold)
        for _ in range(config.degraded_dispatch_budget + 5):
            store_breaker.should_shed()

        assert (
            store_breaker.state()["degradedDispatches"]
            == config.degraded_dispatch_budget
        )


class TestRecovery:
    def test_a_single_success_closes_the_breaker(self):
        """Threshold failures then one success leaves it closed.

        The case being defended against is a partition, which looks like an
        unbroken run. A store failing one call in ten is degraded but still
        metering, and shedding for that is the self-inflicted outage every
        fail-open here exists to avoid.
        """
        import config
        from ops import store_breaker

        _fail(config.store_failure_threshold)
        store_breaker.record_store_result(True)

        assert store_breaker.state()["consecutiveFailures"] == 0
        assert store_breaker.should_shed() is False

    def test_failures_must_be_consecutive(self):
        import config
        from ops import store_breaker

        for _ in range(config.store_failure_threshold * 3):
            store_breaker.record_store_result(False)
            store_breaker.record_store_result(True)

        assert store_breaker.should_shed() is False
        assert store_breaker.state()["degradedDispatches"] == 0

    def test_a_success_does_not_refund_the_degraded_budget(self):
        """Documented as deliberate in the module: resetting the dispatch
        budget on every recovery would give a flapping store an unbounded
        allowance, which is the one thing this cannot permit."""
        import config
        from ops import store_breaker

        _fail(config.store_failure_threshold)
        store_breaker.should_shed()
        spent = store_breaker.state()["degradedDispatches"]

        store_breaker.record_store_result(True)

        assert store_breaker.state()["degradedDispatches"] == spent


class TestResetIsForTests:
    def test_reset_clears_both_counters(self):
        import config
        from ops import store_breaker

        _fail(config.store_failure_threshold)
        store_breaker.should_shed()

        store_breaker.reset()

        assert store_breaker.state() == {
            "consecutiveFailures": 0,
            "degradedDispatches": 0,
        }

    def test_nothing_in_the_request_path_calls_reset(self):
        """A breaker something can switch off is not a breaker."""
        import pathlib

        src = pathlib.Path(__file__).resolve().parents[3] / "backend" / "src"
        callers = [
            str(path.relative_to(src))
            for path in src.rglob("*.py")
            if path.name != "store_breaker.py"
            and "store_breaker.reset()" in path.read_text()
        ]
        assert callers == []


class TestConfiguration:
    def test_the_thresholds_are_configurable_and_positive(self):
        import config

        assert config.store_failure_threshold > 0
        assert config.degraded_dispatch_budget > 0

    def test_the_degraded_budget_is_a_backstop_not_a_second_ceiling(self):
        """20 generations at roughly $0.19 is about $3.80 per container, ten
        containers about $38, against a $25 daily ceiling. It should never
        bind while DynamoDB is healthy, which is what the threshold buys."""
        import config

        assert config.degraded_dispatch_budget > config.store_failure_threshold


# ---------------------------------------------------------------------------
# Every fail-open site must actually record its failure.
#
# The end-to-end test in test_spend_ceiling.py cannot prove this: four other
# sites fire on the same request, so removing any single one only delays the
# trip and the test still passes. Verified by mutation -- deleting
# record_store_result(False) from each of the six sites in turn left it
# green. These drive each guard in isolation, which is the only way a missing
# site is visible, and an under-counting breaker is exactly the failure the
# task warns about.
# ---------------------------------------------------------------------------


class _Boom(RuntimeError):
    pass


def _exploding_repo():
    from unittest.mock import MagicMock

    repo = MagicMock()
    repo.get_user.side_effect = _Boom("dynamodb partition")
    repo.add_counters.side_effect = _Boom("dynamodb partition")
    repo.increment_anon.side_effect = _Boom("dynamodb partition")
    return repo


def _drive_daily_ceiling():
    from unittest.mock import patch

    import lambda_function as lf

    with patch.object(lf._cost_meter, "get_daily_spend", side_effect=_Boom("down")):
        lf._daily_spend_exceeded(now=1784980800)


def _drive_monthly_ceiling():
    from unittest.mock import patch

    import lambda_function as lf

    with patch.object(lf._cost_meter, "get_monthly_spend", side_effect=_Boom("down")):
        lf._monthly_spend_exceeded(now=1784980800)


def _drive_enhance_ceiling():
    from unittest.mock import patch

    import lambda_function as lf

    with patch.object(lf._cost_meter, "get_daily_spend", side_effect=_Boom("down")):
        lf._enhance_spend_exceeded(now=1784980800)


def _drive_tier_quota():
    from unittest.mock import patch

    import lambda_function as lf
    from users.tier import TierContext

    ctx = TierContext(
        tier="free",
        user_id="u1",
        email=None,
        is_authenticated=True,
        guest_token_id=None,
        issue_guest_cookie=False,
    )
    with patch.object(lf, "enforce_quota", side_effect=_Boom("down")):
        lf._enforce_quota_safe(ctx, "generate", 1784980800)


def _drive_anon_quota():
    from users.quota import enforce_quota
    from users.tier import TierContext

    ctx = TierContext(
        tier="anon",
        user_id="anon#abc",
        email=None,
        is_authenticated=False,
        guest_token_id=None,
        issue_guest_cookie=False,
        ip_hash="abc",
    )
    enforce_quota(ctx, "generate", _exploding_repo(), 1784980800)


def _drive_cost_meter():
    from ops.cost_meter import CostMeter

    CostMeter(_exploding_repo()).record(
        costs={"gemini": 39000}, tier="anon", user_id="u1", now=1784980800
    )


def _drive_per_model_cap():
    import json
    from unittest.mock import MagicMock, patch

    import lambda_function as lf
    from users.quota import QuotaResult

    healthy = MagicMock()
    healthy.get_model_runtime_config.return_value = None

    with (
        patch.object(lf, "_spend_ceiling_exceeded", return_value=(False, "")),
        patch.object(lf, "enforce_quota", return_value=QuotaResult(True, None, 0)),
        patch.object(lf, "content_filter") as cf,
        patch.object(lf, "_user_repo", healthy),
        patch.object(lf, "_model_counter_service") as counter,
        patch.object(lf, "session_manager") as sm,
        patch.object(lf, "_prompt_history"),
        patch.object(lf.config, "generate_async", True),
        patch.object(lf, "_dispatch_generation_async", return_value=True),
    ):
        cf.check_prompt.return_value = False
        counter.consume_model_slot.side_effect = _Boom("dynamodb partition")
        sm.create_session.return_value = "s1"
        lf.handle_generate(
            {
                "body": json.dumps({"prompt": "a cat"}),
                "requestContext": {"http": {"sourceIp": "10.0.0.1"}},
                "headers": {},
            },
            "corr-site",
        )


@pytest.mark.parametrize(
    "site,drive",
    [
        ("_daily_spend_exceeded", _drive_daily_ceiling),
        ("_monthly_spend_exceeded", _drive_monthly_ceiling),
        ("_enhance_spend_exceeded", _drive_enhance_ceiling),
        ("_enforce_quota_safe", _drive_tier_quota),
        ("per-model cap filter loop", _drive_per_model_cap),
        ("users.quota._enforce_anon", _drive_anon_quota),
        ("ops.cost_meter.CostMeter.record", _drive_cost_meter),
    ],
)
def test_every_fail_open_site_records_its_store_failure(site, drive):
    """One site per row. Adding an eighth fail-open guard without a row here
    makes the breaker under-count, silently."""
    from ops import store_breaker

    store_breaker.reset()
    drive()

    assert store_breaker.state()["consecutiveFailures"] >= 1, (
        f"{site} swallowed a store error without recording it"
    )


def test_a_healthy_guard_records_a_success_that_closes_the_breaker():
    """The counterpart: the sites must record successes too, or a healthy
    store would leave a stale failure count in place forever."""
    from unittest.mock import patch

    import lambda_function as lf
    from ops import store_breaker

    store_breaker.reset()
    for _ in range(20):
        store_breaker.record_store_result(False)

    with patch.object(lf._cost_meter, "get_daily_spend", return_value={"totalMicros": 0}):
        lf._daily_spend_exceeded(now=1784980800)

    assert store_breaker.state()["consecutiveFailures"] == 0
