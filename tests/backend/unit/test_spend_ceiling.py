"""Tests for the global daily spend ceiling.

This is the only cost guard in the system that is not conditional on
AUTH_ENABLED. Every other one is, which is precisely why a default deploy
previously had no spend bound at all.
"""

from __future__ import annotations

import importlib
import json
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("CLOUDFRONT_DOMAIN", "test.cloudfront.net")


def _event(prompt="a cat"):
    return {
        "body": json.dumps({"prompt": prompt}),
        "requestContext": {"http": {"sourceIp": "127.0.0.1"}},
        "headers": {},
    }


def test_ceiling_defaults_to_on():
    """A default deploy must have a spend bound.

    Defaulting this off would repeat the mistake that left the shipped
    configuration with no cost protection whatsoever.
    """
    import config

    importlib.reload(config)
    assert config.global_daily_spend_ceiling_usd_micros == 25_000_000  # $25/day


def test_ceiling_is_env_tunable(monkeypatch):
    monkeypatch.setenv("GLOBAL_DAILY_SPEND_CEILING_USD_MICROS", "5000000")
    import config

    importlib.reload(config)
    try:
        assert config.global_daily_spend_ceiling_usd_micros == 5_000_000
    finally:
        monkeypatch.delenv("GLOBAL_DAILY_SPEND_CEILING_USD_MICROS", raising=False)
        importlib.reload(config)


def test_zero_disables_the_ceiling():
    import lambda_function

    with patch("config.global_daily_spend_ceiling_usd_micros", 0):
        assert lambda_function._daily_spend_exceeded() is False


def test_under_ceiling_allows():
    import lambda_function

    with (
        patch("config.global_daily_spend_ceiling_usd_micros", 1_000_000),
        patch.object(
            lambda_function._cost_meter,
            "get_daily_spend",
            return_value={"totalMicros": 999_999},
        ),
    ):
        assert lambda_function._daily_spend_exceeded() is False


def test_at_ceiling_blocks():
    import lambda_function

    with (
        patch("config.global_daily_spend_ceiling_usd_micros", 1_000_000),
        patch.object(
            lambda_function._cost_meter,
            "get_daily_spend",
            return_value={"totalMicros": 1_000_000},
        ),
    ):
        assert lambda_function._daily_spend_exceeded() is True


def test_read_failure_fails_open():
    """A DynamoDB blip must not take the whole service down.

    We cannot prove the budget is blown, and hard-failing every billable
    request on an unreadable counter is a self-inflicted outage.
    """
    import lambda_function

    with (
        patch("config.global_daily_spend_ceiling_usd_micros", 1_000_000),
        patch.object(
            lambda_function._cost_meter,
            "get_daily_spend",
            side_effect=RuntimeError("dynamo down"),
        ),
    ):
        assert lambda_function._daily_spend_exceeded() is False


def test_generate_returns_503_when_ceiling_reached():
    import lambda_function

    with (
        patch("lambda_function._daily_spend_exceeded", return_value=True),
        patch("lambda_function.content_filter") as mock_cf,
    ):
        mock_cf.check_prompt.return_value = False
        resp = lambda_function.handle_generate(_event(), "corr-1")

    assert resp["statusCode"] == 503
    assert json.loads(resp["body"])["error"] == "DAILY_SPEND_CEILING"


def test_enhance_returns_503_when_ceiling_reached():
    """/enhance is unauthenticated and unquota'd, so the ceiling is its only bound."""
    import lambda_function

    with (
        patch("lambda_function._daily_spend_exceeded", return_value=True),
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function.prompt_enhancer") as mock_enh,
    ):
        mock_cf.check_prompt.return_value = False
        resp = lambda_function.handle_enhance(_event(), "corr-1")

    assert resp["statusCode"] == 503
    # The expensive call must not have happened.
    mock_enh.enhance_safe.assert_not_called()


def test_ceiling_applies_with_auth_disabled():
    """The whole point: this guard is not conditional on AUTH_ENABLED."""
    import lambda_function

    with (
        patch("config.auth_enabled", False),
        patch("lambda_function._daily_spend_exceeded", return_value=True),
        patch("lambda_function.content_filter") as mock_cf,
    ):
        mock_cf.check_prompt.return_value = False
        resp = lambda_function.handle_generate(_event(), "corr-1")

    assert resp["statusCode"] == 503


def test_status_endpoint_is_not_blocked_by_ceiling():
    """Read-only endpoints cost nothing and must stay available."""
    import lambda_function

    with (
        patch("lambda_function._daily_spend_exceeded", return_value=True) as mock_check,
        patch("lambda_function.session_manager") as mock_sm,
    ):
        mock_sm.get_session.return_value = {"sessionId": "s1", "models": {}}
        lambda_function.handle_status(
            {
                "rawPath": "/status/s1",
                "pathParameters": {"sessionId": "s1"},
                "requestContext": {"http": {"method": "GET", "sourceIp": "1.2.3.4"}},
                "headers": {},
            },
            "corr-1",
        )
    mock_check.assert_not_called()


def test_ceiling_checked_before_provider_dispatch():
    """Rejection must happen before any model is called, or it saves nothing."""
    import lambda_function

    with (
        patch("lambda_function._daily_spend_exceeded", return_value=True),
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function._executor") as mock_exec,
        patch("lambda_function.session_manager") as mock_sm,
    ):
        mock_cf.check_prompt.return_value = False
        resp = lambda_function.handle_generate(_event(), "corr-1")

    assert resp["statusCode"] == 503
    mock_exec.submit.assert_not_called()
    mock_sm.create_session.assert_not_called()


def test_ceiling_uses_live_accumulator(monkeypatch):
    """End to end: metered spend feeds the ceiling decision."""
    import boto3
    from moto import mock_aws

    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="spend-ceiling-test",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        from ops.cost_meter import CostMeter
        from users.repository import UserRepository

        repo = UserRepository("spend-ceiling-test", dynamodb_resource=ddb)
        meter = CostMeter(repo)
        now = 1784980800

        import lambda_function

        with (
            patch("config.global_daily_spend_ceiling_usd_micros", 100_000),
            patch.object(lambda_function, "_cost_meter", meter),
        ):
            assert lambda_function._daily_spend_exceeded(now=now) is False
            meter.record(costs={"gemini": 60_000}, tier="paid", now=now)
            assert lambda_function._daily_spend_exceeded(now=now) is False
            meter.record(costs={"nova": 60_000}, tier="paid", now=now)
            assert lambda_function._daily_spend_exceeded(now=now) is True


# ---- /enhance sub-ceiling ----


def test_enhance_sub_ceiling_defaults_on():
    import config

    importlib.reload(config)
    assert config.enhance_daily_spend_ceiling_usd_micros == 2_000_000  # $2/day


def test_enhance_blocked_by_its_own_ceiling_while_generate_still_works():
    """The point: unauthenticated /enhance must not be able to 503 paying users.

    Metering /enhance against the shared budget alone would let anonymous
    traffic exhaust the day's spend and deny service to /generate — a cost
    guard doubling as a DoS amplifier.
    """
    import lambda_function

    # Enhance has burned its sub-budget; global budget is nowhere near spent.
    spend = {"totalMicros": 1_000_000, "enhanceMicros": 5_000_000}
    with (
        patch("config.global_daily_spend_ceiling_usd_micros", 100_000_000),
        patch("config.enhance_daily_spend_ceiling_usd_micros", 5_000_000),
        patch.object(lambda_function._cost_meter, "get_daily_spend", return_value=spend),
    ):
        assert lambda_function._spend_ceiling_exceeded("enhance")[0] is True
        assert lambda_function._spend_ceiling_exceeded("generate")[0] is False
        assert lambda_function._spend_ceiling_exceeded("refine")[0] is False


def test_global_ceiling_still_blocks_enhance():
    import lambda_function

    spend = {"totalMicros": 100_000_000, "enhanceMicros": 0}
    with (
        patch("config.global_daily_spend_ceiling_usd_micros", 100_000_000),
        patch("config.enhance_daily_spend_ceiling_usd_micros", 5_000_000),
        patch.object(lambda_function._cost_meter, "get_daily_spend", return_value=spend),
    ):
        exceeded, scope = lambda_function._spend_ceiling_exceeded("enhance")
        assert exceeded is True
        assert scope == "Global"


def test_enhance_sub_ceiling_zero_disables():
    import lambda_function

    spend = {"totalMicros": 0, "enhanceMicros": 999_000_000}
    with (
        patch("config.global_daily_spend_ceiling_usd_micros", 100_000_000),
        patch("config.enhance_daily_spend_ceiling_usd_micros", 0),
        patch.object(lambda_function._cost_meter, "get_daily_spend", return_value=spend),
    ):
        assert lambda_function._spend_ceiling_exceeded("enhance")[0] is False


def test_enhance_sub_ceiling_fails_open():
    import lambda_function

    with (
        patch("config.enhance_daily_spend_ceiling_usd_micros", 1_000),
        patch.object(
            lambda_function._cost_meter,
            "get_daily_spend",
            side_effect=RuntimeError("dynamo down"),
        ),
    ):
        assert lambda_function._enhance_spend_exceeded() is False


# ---- Response shape ----


def test_ceiling_response_tells_clients_when_to_retry():
    """The reset is deterministic (UTC midnight), so say so."""
    from utils import error_responses

    body = error_responses.daily_spend_ceiling()
    assert body["error"] == "DAILY_SPEND_CEILING"
    retry = body.get("retryAfter") or body.get("retry_after")
    assert retry is not None
    assert 0 < int(retry) <= 86400


# ---- Accumulator retention ----


def test_spend_items_expire():
    """A cost-control feature must not itself grow the table forever."""
    import boto3
    from moto import mock_aws

    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="spend-ttl-test",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        from ops.cost_meter import SPEND_ITEM_TTL_SECONDS, CostMeter, spend_item_key
        from users.repository import UserRepository

        repo = UserRepository("spend-ttl-test", dynamodb_resource=ddb)
        meter = CostMeter(repo)
        now = 1784980800
        meter.record(costs={"gemini": 39000}, tier="paid", now=now)

        item = repo.get_user(spend_item_key(now))
        assert int(item["ttl"]) == now + SPEND_ITEM_TTL_SECONDS

        # A later write must not push the expiry out indefinitely.
        meter.record(costs={"gemini": 39000}, tier="paid", now=now + 3600)
        item = repo.get_user(spend_item_key(now))
        assert int(item["ttl"]) == now + SPEND_ITEM_TTL_SECONDS
        assert int(item["totalMicros"]) == 78000


# ---- Monthly ceiling ----


def test_monthly_ceiling_defaults_to_500_dollars():
    """The number that actually caps the invoice.

    A daily ceiling alone does not bound a month: even at $25/day it permits
    roughly $750 across 30 days, so the monthly figure has to exist
    separately rather than be inferred.
    """
    import config

    importlib.reload(config)
    assert config.monthly_spend_ceiling_usd_micros == 500_000_000


def test_daily_ceiling_leaves_burst_headroom_under_the_month():
    """Deliberately more than 1/30th of the month.

    A busy day should not be throttled for being busy; the month is what
    stops. But a single day must not be able to consume the whole budget.
    """
    import config

    importlib.reload(config)
    daily = config.global_daily_spend_ceiling_usd_micros
    monthly = config.monthly_spend_ceiling_usd_micros
    assert daily > monthly / 30, "no burst headroom"
    assert daily < monthly / 2, "one day could eat the month"


def test_enhance_share_of_the_monthly_budget_is_bounded():
    """/enhance is unauthenticated, so its share must be a minority."""
    import config

    importlib.reload(config)
    enhance_month = config.enhance_daily_spend_ceiling_usd_micros * 30
    assert enhance_month < config.monthly_spend_ceiling_usd_micros * 0.2


def test_monthly_ceiling_blocks_when_reached():
    import lambda_function

    with (
        patch("config.monthly_spend_ceiling_usd_micros", 500_000_000),
        patch.object(
            lambda_function._cost_meter,
            "get_monthly_spend",
            return_value={"totalMicros": 500_000_000},
        ),
    ):
        assert lambda_function._monthly_spend_exceeded() is True


def test_monthly_ceiling_allows_under_budget():
    import lambda_function

    with (
        patch("config.monthly_spend_ceiling_usd_micros", 500_000_000),
        patch.object(
            lambda_function._cost_meter,
            "get_monthly_spend",
            return_value={"totalMicros": 499_999_999},
        ),
    ):
        assert lambda_function._monthly_spend_exceeded() is False


def test_monthly_breach_reports_itself_as_monthly():
    """An operator seeing "Global" would look at the wrong dashboard."""
    import lambda_function

    with (
        patch("lambda_function._monthly_spend_exceeded", return_value=True),
        patch("lambda_function._daily_spend_exceeded", return_value=False),
    ):
        exceeded, scope = lambda_function._spend_ceiling_exceeded("generate")
    assert exceeded is True
    assert scope == "Monthly"


def test_monthly_ceiling_fails_open():
    import lambda_function

    with (
        patch("config.monthly_spend_ceiling_usd_micros", 1_000),
        patch.object(
            lambda_function._cost_meter,
            "get_monthly_spend",
            side_effect=RuntimeError("dynamo down"),
        ),
    ):
        assert lambda_function._monthly_spend_exceeded() is False


def test_zero_disables_the_monthly_ceiling():
    import lambda_function

    with patch("config.monthly_spend_ceiling_usd_micros", 0):
        assert lambda_function._monthly_spend_exceeded() is False


def test_generate_returns_503_when_the_month_is_spent():
    import lambda_function

    with (
        patch("lambda_function._monthly_spend_exceeded", return_value=True),
        patch("lambda_function.content_filter") as mock_cf,
    ):
        mock_cf.check_prompt.return_value = False
        resp = lambda_function.handle_generate(_event(), "corr-1")

    assert resp["statusCode"] == 503
    assert json.loads(resp["body"])["error"] == "DAILY_SPEND_CEILING"


def test_monthly_spend_accumulates_separately_from_daily():
    """Days roll over; the month must not."""
    import boto3
    from moto import mock_aws

    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="monthly-test",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        from ops.cost_meter import CostMeter
        from users.repository import UserRepository

        meter = CostMeter(UserRepository("monthly-test", dynamodb_resource=ddb))
        day1 = 1784980800  # 2026-07-25
        day2 = day1 + 86400  # 2026-07-26, same month

        meter.record(costs={"gemini": 40_000}, tier="paid", now=day1)
        meter.record(costs={"gemini": 60_000}, tier="paid", now=day2)

        assert meter.get_daily_spend(now=day1)["totalMicros"] == 40_000
        assert meter.get_daily_spend(now=day2)["totalMicros"] == 60_000
        assert meter.get_monthly_spend(now=day2)["totalMicros"] == 100_000


def test_a_new_month_starts_from_zero():
    import boto3
    from moto import mock_aws

    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="monthly-test2",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        from ops.cost_meter import CostMeter
        from users.repository import UserRepository

        meter = CostMeter(UserRepository("monthly-test2", dynamodb_resource=ddb))
        july = 1784980800
        august = july + (10 * 86400)  # 2026-08-04

        meter.record(costs={"gemini": 90_000}, tier="paid", now=july)
        assert meter.get_monthly_spend(now=july)["totalMicros"] == 90_000
        assert meter.get_monthly_spend(now=august)["totalMicros"] == 0


# ---- Monthly cache reconciliation ----


def _spend_repo(name):
    import boto3
    from moto import mock_aws

    ctx = mock_aws()
    ctx.start()
    ddb = boto3.resource("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName=name,
        KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    from users.repository import UserRepository

    return ctx, UserRepository(name, dynamodb_resource=ddb)


def test_reconciliation_repairs_an_undercounting_month():
    """The monthly item is a cache; the daily items are authoritative.

    An under-counting monthly total means the ceiling that caps the invoice
    trips later than it should, so drift has to be corrected rather than
    tolerated.
    """
    from ops.cost_meter import CostMeter, monthly_spend_item_key, reconcile_monthly_spend

    ctx, repo = _spend_repo("recon-1")
    try:
        meter = CostMeter(repo)
        now = 1784980800  # 2026-07-25
        meter.record(costs={"gemini": 40_000}, tier="paid", now=now - 86400)
        meter.record(costs={"gemini": 60_000}, tier="paid", now=now)

        # Simulate the monthly write having failed for one of those days.
        repo.add_counters(monthly_spend_item_key(now), {"totalMicros": -60_000}, now=now)
        assert meter.get_monthly_spend(now=now)["totalMicros"] == 40_000

        result = reconcile_monthly_spend(repo, now)

        assert result["expected"] == 100_000
        assert result["corrected"] == 60_000
        assert meter.get_monthly_spend(now=now)["totalMicros"] == 100_000
    finally:
        ctx.stop()


def test_reconciliation_is_a_noop_when_consistent():
    from ops.cost_meter import CostMeter, reconcile_monthly_spend

    ctx, repo = _spend_repo("recon-2")
    try:
        meter = CostMeter(repo)
        now = 1784980800
        meter.record(costs={"gemini": 40_000}, tier="paid", now=now)

        result = reconcile_monthly_spend(repo, now)
        assert result["corrected"] == 0
        assert meter.get_monthly_spend(now=now)["totalMicros"] == 40_000
    finally:
        ctx.stop()


def test_reconciliation_does_not_reach_into_the_previous_month():
    """Walking back must stop at the month boundary, not 31 days."""
    from ops.cost_meter import CostMeter, reconcile_monthly_spend

    ctx, repo = _spend_repo("recon-3")
    try:
        meter = CostMeter(repo)
        july_25 = 1784980800
        june_28 = july_25 - (27 * 86400)

        meter.record(costs={"gemini": 99_000}, tier="paid", now=june_28)
        meter.record(costs={"gemini": 10_000}, tier="paid", now=july_25)

        result = reconcile_monthly_spend(repo, july_25)
        assert result["expected"] == 10_000, "pulled in a previous month's spend"
    finally:
        ctx.stop()


# ---------------------------------------------------------------------------
# A corrupt spend item fails CLOSED; a store outage still fails OPEN.
#
# The two are different failures and had one policy. A DynamoDB error is
# transient, and failing open on it is argued in the helpers' docstrings. A
# malformed attribute is permanent: failing open there means the ceiling is
# off until a human reads the logs.
# ---------------------------------------------------------------------------


def test_an_unreadable_daily_total_refuses_the_request(monkeypatch):
    import lambda_function as lf
    from ops.cost_meter import UnreadableSpendTotal

    def _boom(**_kwargs):
        raise UnreadableSpendTotal("totalMicros is not a number")

    monkeypatch.setattr(lf._cost_meter, "get_daily_spend", _boom)
    assert lf._daily_spend_exceeded(now=1784980800) is True


def test_an_unreadable_monthly_total_refuses_the_request(monkeypatch):
    import lambda_function as lf
    from ops.cost_meter import UnreadableSpendTotal

    def _boom(**_kwargs):
        raise UnreadableSpendTotal("totalMicros is not a number")

    monkeypatch.setattr(lf._cost_meter, "get_monthly_spend", _boom)
    assert lf._monthly_spend_exceeded(now=1784980800) is True


def test_an_unreadable_enhance_total_refuses_the_request(monkeypatch):
    import lambda_function as lf
    from ops.cost_meter import UnreadableSpendTotal

    def _boom(**_kwargs):
        raise UnreadableSpendTotal("enhanceMicros is not a number")

    monkeypatch.setattr(lf._cost_meter, "get_daily_spend", _boom)
    assert lf._enhance_spend_exceeded(now=1784980800) is True


def test_a_store_error_still_fails_open(monkeypatch):
    """The documented policy for a transient DynamoDB failure is unchanged.

    This is the assertion that stops the fail-closed case above being widened
    into a self-inflicted outage on a blip.
    """
    import lambda_function as lf

    def _boom(**_kwargs):
        raise RuntimeError("dynamodb unavailable")

    monkeypatch.setattr(lf._cost_meter, "get_daily_spend", _boom)
    monkeypatch.setattr(lf._cost_meter, "get_monthly_spend", _boom)
    assert lf._daily_spend_exceeded(now=1784980800) is False
    assert lf._monthly_spend_exceeded(now=1784980800) is False
    assert lf._enhance_spend_exceeded(now=1784980800) is False


# ---------------------------------------------------------------------------
# The bound that does not read DynamoDB.
#
# Six guards fail open on a store error and spend recording silently stops,
# and they all share one table -- so a single partition problem opens every
# gate AND stops the accounting, leaving an SNS email as the only signal. At
# the API Gateway throttle ceiling that is roughly $2k/day against a $500
# monthly ceiling.
# ---------------------------------------------------------------------------


@pytest.fixture
def _clean_breaker():
    from ops import store_breaker

    store_breaker.reset()
    yield store_breaker
    store_breaker.reset()


def test_generate_stops_dispatching_once_the_store_has_been_down_and_the_degraded_budget_is_spent(
    _clean_breaker, monkeypatch
):
    """The finding, stated as a test.

    Every store call raises, so every guard fails open and every one of them
    records a failure. The first `degraded_dispatch_budget` generations still
    dispatch -- deliberately, because a store blip must not deny service --
    and the next one is shed.
    """
    import importlib
    import json as _json
    from unittest.mock import MagicMock, patch

    import config
    import lambda_function as lf

    importlib.reload(config)

    exploding = MagicMock()
    exploding.get_user.side_effect = RuntimeError("dynamodb partition")
    exploding.add_counters.side_effect = RuntimeError("dynamodb partition")
    exploding.increment_anon.side_effect = RuntimeError("dynamodb partition")
    exploding.get_model_runtime_config.side_effect = RuntimeError("dynamodb partition")

    def _event():
        return {
            "body": _json.dumps({"prompt": "a cat"}),
            "requestContext": {"http": {"sourceIp": "10.0.0.1"}},
            "headers": {},
        }

    dispatched = []
    statuses = []
    attempts = config.degraded_dispatch_budget + 6
    with (
        patch.object(lf, "_user_repo", exploding),
        patch.object(lf._cost_meter, "_repo", exploding),
        patch.object(lf._model_counter_service, "_repo", exploding, create=True),
        patch.object(lf, "session_manager") as mock_sm,
        patch.object(lf, "_prompt_history"),
        patch.object(lf.config, "generate_async", True),
        patch.object(lf, "_dispatch_generation_async", side_effect=lambda *a, **k: (
            dispatched.append(1) or True
        )),
    ):
        mock_sm.create_session.return_value = "s1"
        for _ in range(attempts):
            statuses.append(lf.handle_generate(_event(), "corr-shed")["statusCode"])

    assert statuses[0] == 202, statuses[:3]
    assert 503 in statuses, "the breaker never shed"
    assert statuses.count(503) >= 1
    # Everything after the first shed stays shed.
    first_shed = statuses.index(503)
    assert set(statuses[first_shed:]) == {503}
    # Requests made BEFORE the breaker tripped are normal dispatches, not
    # degraded ones -- the counter needs store_failure_threshold consecutive
    # failures and one /generate produces four, so the first request or two
    # run before it trips. What the budget bounds is the dispatches made
    # while tripped, which is exactly what the breaker's own counter reports.
    assert _clean_breaker.state()["degradedDispatches"] == config.degraded_dispatch_budget
    assert len(dispatched) < attempts


def test_the_shed_response_is_distinguishable_from_the_daily_ceiling(_clean_breaker):
    """Two different operator responses -- raise the ceiling, or fix DynamoDB
    -- so the two 503s must be separable in the logs."""
    import json as _json

    from utils import error_responses

    degraded = _json.loads(_json.dumps(error_responses.spend_guard_degraded()))
    ceiling = _json.loads(_json.dumps(error_responses.daily_spend_ceiling()))

    assert degraded["error"] == "SPEND_GUARD_DEGRADED"
    assert ceiling["error"] == "DAILY_SPEND_CEILING"
    assert degraded["error"] != ceiling["error"]


def test_a_shed_generate_reaches_no_provider_handler(_clean_breaker, monkeypatch):
    """With should_shed forced True, no provider is called at all.

    A test that only checked the status code would pass against an
    implementation that refuses the caller after dispatching, which is the
    exact failure the breaker exists to prevent.
    """
    import json as _json
    from unittest.mock import MagicMock, patch

    import lambda_function as lf

    with (
        patch.object(lf.store_breaker, "should_shed", return_value=True),
        patch.object(lf, "_spend_ceiling_exceeded", return_value=(False, "")),
        patch.object(lf, "enforce_quota") as mock_quota,
        patch.object(lf, "content_filter") as mock_cf,
        patch.object(lf, "_user_repo", MagicMock()),
        patch.object(lf, "get_enabled_models") as mock_models,
        patch.object(lf, "session_manager") as mock_sm,
        patch.object(lf, "get_handler") as mock_handler,
        patch.object(lf, "_dispatch_generation_async") as mock_dispatch,
        patch.object(lf, "_refund_usage") as mock_refund,
    ):
        from users.quota import QuotaResult

        mock_quota.return_value = QuotaResult(allowed=True, reason=None, reset_at=0)
        mock_cf.check_prompt.return_value = False

        resp = lf.handle_generate(
            {
                "body": _json.dumps({"prompt": "a cat"}),
                "requestContext": {"http": {"sourceIp": "10.0.0.1"}},
                "headers": {},
            },
            "corr-forced",
        )

    assert resp["statusCode"] == 503
    assert _json.loads(resp["body"])["error"] == "SPEND_GUARD_DEGRADED"
    mock_handler.assert_not_called()
    mock_dispatch.assert_not_called()
    mock_models.assert_not_called()
    mock_sm.create_session.assert_not_called()
    # An early exit that never reaches a provider must refund, per the
    # _refund_usage invariant.
    mock_refund.assert_called_once()


def test_a_healthy_store_never_sheds(_clean_breaker):
    """A breaker that fires in the healthy case is worse than none."""
    import json as _json
    from unittest.mock import MagicMock, patch

    import config
    import lambda_function as lf

    healthy = MagicMock()
    healthy.get_user.return_value = None
    healthy.get_model_runtime_config.return_value = None

    statuses = []
    with (
        patch.object(lf, "_user_repo", healthy),
        patch.object(lf._cost_meter, "_repo", healthy),
        patch.object(lf, "session_manager") as mock_sm,
        patch.object(lf, "_prompt_history"),
        patch.object(lf, "enforce_quota") as mock_quota,
        patch.object(lf, "_model_counter_service") as mock_counter,
        patch.object(lf.config, "generate_async", True),
        patch.object(lf, "_dispatch_generation_async", return_value=True),
    ):
        from users.quota import QuotaResult

        mock_quota.return_value = QuotaResult(allowed=True, reason=None, reset_at=0)
        mock_counter.consume_model_slot.return_value = True
        mock_sm.create_session.return_value = "s1"
        for _ in range(config.degraded_dispatch_budget * 3):
            statuses.append(
                lf.handle_generate(
                    {
                        "body": _json.dumps({"prompt": "a cat"}),
                        "requestContext": {"http": {"sourceIp": "10.0.0.1"}},
                        "headers": {},
                    },
                    "corr-healthy",
                )["statusCode"]
            )

    assert 503 not in statuses
    assert _clean_breaker.state()["degradedDispatches"] == 0
