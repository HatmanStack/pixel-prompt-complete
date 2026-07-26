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
