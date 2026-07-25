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
    assert config.global_daily_spend_ceiling_usd_micros == 100_000_000  # $100/day


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
