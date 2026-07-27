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
