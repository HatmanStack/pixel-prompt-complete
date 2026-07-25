"""Tests that admin surfaces report dollars, not just counts.

The audit's framing was that neither cost landmine was visible from the admin
dashboard. Counts cannot show it: a generate costs ~4x a refine and providers
differ ~2x, so call volume can move opposite to actual spend.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

TABLE_NAME = "pixel-prompt-users-adminspend"


@pytest.fixture
def repo():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        from users.repository import UserRepository

        yield UserRepository(TABLE_NAME, dynamodb_resource=ddb)


def _admin_event(path="/admin/metrics"):
    return {
        "rawPath": path,
        "requestContext": {
            "http": {"method": "GET", "sourceIp": "127.0.0.1"},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "admin-user-1",
                        "email": "admin@example.com",
                        "cognito:groups": ["admins"],
                    }
                }
            },
        },
        "headers": {},
        "queryStringParameters": {"days": "3"},
    }


def _seed(repo, now):
    from ops.cost_meter import CostMeter

    meter = CostMeter(repo)
    meter.record(costs={"gemini": 39000, "nova": 40000}, tier="paid", now=now)
    meter.record(costs={"firefly": 70000}, tier="free", now=now)
    meter.record(costs={"enhance": 7000}, tier="guest", now=now)
    return meter


def test_metrics_reports_dollar_spend(repo):
    import time as _t

    from admin.metrics import handle_admin_metrics
    from ops.model_counters import ModelCounterService

    now = int(_t.time())
    _seed(repo, now)

    with patch("config.admin_enabled", True), patch("config.auth_enabled", True):
        resp = handle_admin_metrics(_admin_event(), repo, ModelCounterService(repo))

    assert resp["statusCode"] == 200
    spend = json.loads(resp["body"])["spend"]
    assert spend["todayMicros"] == 156000
    assert spend["todayUsd"] == 0.156


def test_spend_broken_down_by_model(repo):
    import time as _t

    from admin.metrics import handle_admin_metrics
    from ops.model_counters import ModelCounterService

    now = int(_t.time())
    _seed(repo, now)

    with patch("config.admin_enabled", True), patch("config.auth_enabled", True):
        resp = handle_admin_metrics(_admin_event(), repo, ModelCounterService(repo))

    by_model = json.loads(resp["body"])["spend"]["byModelMicros"]
    assert by_model["gemini"] == 39000
    assert by_model["firefly"] == 70000
    assert by_model["openai"] == 0


def test_free_tier_spend_gets_its_own_line(repo):
    """Free-tier spend is pure acquisition cost and the largest exposure."""
    import time as _t

    from admin.metrics import handle_admin_metrics
    from ops.model_counters import ModelCounterService

    now = int(_t.time())
    _seed(repo, now)

    with patch("config.admin_enabled", True), patch("config.auth_enabled", True):
        resp = handle_admin_metrics(_admin_event(), repo, ModelCounterService(repo))

    spend = json.loads(resp["body"])["spend"]
    assert spend["freeTierMicros"] == 70000
    assert spend["byTierMicros"]["paid"] == 79000


def test_ceiling_utilisation_is_visible(repo):
    """An operator should see how close today is to tripping the ceiling."""
    import time as _t

    from admin.metrics import handle_admin_metrics
    from ops.model_counters import ModelCounterService

    now = int(_t.time())
    _seed(repo, now)

    with (
        patch("config.admin_enabled", True),
        patch("config.auth_enabled", True),
        patch("config.global_daily_spend_ceiling_usd_micros", 312000),
    ):
        resp = handle_admin_metrics(_admin_event(), repo, ModelCounterService(repo))

    spend = json.loads(resp["body"])["spend"]
    assert spend["dailyCeilingMicros"] == 312000
    assert spend["dailyCeilingUsedPct"] == 50.0


def test_ceiling_pct_is_none_when_disabled(repo):
    import time as _t

    from admin.metrics import handle_admin_metrics
    from ops.model_counters import ModelCounterService

    _seed(repo, int(_t.time()))
    with (
        patch("config.admin_enabled", True),
        patch("config.auth_enabled", True),
        patch("config.global_daily_spend_ceiling_usd_micros", 0),
    ):
        resp = handle_admin_metrics(_admin_event(), repo, ModelCounterService(repo))
    assert json.loads(resp["body"])["spend"]["dailyCeilingUsedPct"] is None


def test_revenue_endpoint_reports_cost_alongside_revenue(repo):
    """Margin needs both sides; revenue alone is half the picture."""
    import time as _t

    from admin.metrics import handle_admin_revenue

    _seed(repo, int(_t.time()))
    repo.increment_revenue_counter("activeSubscribers", 3)

    with patch("config.admin_enabled", True), patch("config.auth_enabled", True):
        resp = handle_admin_revenue(_admin_event(), repo)

    body = json.loads(resp["body"])
    assert body["current"]["activeSubscribers"] == 3
    assert body["spend"]["todayMicros"] == 156000


def test_spend_window_sums_multiple_days(repo):
    import time as _t

    from admin.metrics import handle_admin_metrics
    from ops.cost_meter import CostMeter
    from ops.model_counters import ModelCounterService

    now = int(_t.time())
    meter = CostMeter(repo)
    meter.record(costs={"gemini": 10000}, tier="paid", now=now)
    meter.record(costs={"gemini": 20000}, tier="paid", now=now - 86400)
    meter.record(costs={"gemini": 30000}, tier="paid", now=now - (2 * 86400))

    with patch("config.admin_enabled", True), patch("config.auth_enabled", True):
        resp = handle_admin_metrics(_admin_event(), repo, ModelCounterService(repo))

    spend = json.loads(resp["body"])["spend"]
    assert spend["windowTotalMicros"] == 60000
    assert spend["windowDays"] == 3
    assert len(spend["daily"]) == 3


def test_empty_day_reports_zero_not_error(repo):

    from admin.metrics import handle_admin_metrics
    from ops.model_counters import ModelCounterService

    with patch("config.admin_enabled", True), patch("config.auth_enabled", True):
        resp = handle_admin_metrics(_admin_event(), repo, ModelCounterService(repo))

    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["spend"]["todayMicros"] == 0
