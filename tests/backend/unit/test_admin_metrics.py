"""Tests for admin metrics and revenue endpoints.

Covers:
- Metrics endpoint returns today's model counts and historical snapshots
- Revenue endpoint returns current and historical data
- Missing snapshot days handled gracefully
- Days parameter works correctly
- Admin auth required
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from ops.model_counters import ModelCounterService
from users.repository import UserRepository


def _make_admin_event(
    path: str = "/admin/metrics",
    method: str = "GET",
    query_params: dict | None = None,
    groups: list[str] | None = None,
):
    """Build an API Gateway event with admin JWT claims."""
    if groups is None:
        groups = ["admins"]
    return {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method, "sourceIp": "127.0.0.1"},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "admin-user-1",
                        "email": "admin@example.com",
                        "cognito:groups": groups,
                    }
                }
            },
        },
        "queryStringParameters": query_params or {},
    }


@pytest.fixture
def dynamo_repo():
    """Create a moto DynamoDB table and UserRepository."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-users",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        repo = UserRepository("test-users", dynamodb_resource=dynamodb)
        yield repo


@pytest.fixture
def populated_repo(dynamo_repo):
    """Repo with revenue and metrics snapshot data."""
    now = int(time.time())
    table = dynamo_repo._table

    # Revenue item
    table.put_item(
        Item={
            "userId": "revenue#current",
            "activeSubscribers": 42,
            "mrr": 2100,
            "monthlyChurn": 3,
            "updatedAt": now,
        }
    )

    # Create daily snapshot items for last 3 days
    today = datetime.now(timezone.utc)
    for i in range(3):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        table.put_item(
            Item={
                "userId": f"metrics#{date_str}",
                "modelCounts": {"gemini": 100 - i * 10, "nova": 80 - i * 5},
                "usersByTier": {"free": 100, "paid": 40 + i},
                "suspendedCount": i,
                "revenue": {"activeSubscribers": 42 - i, "monthlyChurn": i},
                "createdAt": now - i * 86400,
            }
        )

    return dynamo_repo


@pytest.fixture
def model_counter(dynamo_repo):
    return ModelCounterService(dynamo_repo)


class TestHandleAdminMetrics:
    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_returns_today_counts_and_history(self, populated_repo, model_counter):
        from admin.metrics import handle_admin_metrics

        event = _make_admin_event(path="/admin/metrics")
        result = handle_admin_metrics(event, populated_repo, model_counter, "corr-1")
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "today" in body
        assert "history" in body
        assert "days" in body

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_days_parameter(self, populated_repo, model_counter):
        from admin.metrics import handle_admin_metrics

        event = _make_admin_event(
            path="/admin/metrics", query_params={"days": "2"}
        )
        result = handle_admin_metrics(event, populated_repo, model_counter, "corr-1")
        body = json.loads(result["body"])
        assert body["days"] == 2
        assert len(body["history"]) <= 2

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_missing_snapshot_days(self, dynamo_repo, model_counter):
        from admin.metrics import handle_admin_metrics

        # No snapshots in DB - should still return without error
        event = _make_admin_event(path="/admin/metrics")
        result = handle_admin_metrics(event, dynamo_repo, model_counter, "corr-1")
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["history"] == []

    @patch("config.admin_enabled", False)
    @patch("config.auth_enabled", True)
    def test_returns_501_when_admin_disabled(self, dynamo_repo, model_counter):
        from admin.metrics import handle_admin_metrics

        event = _make_admin_event(path="/admin/metrics")
        result = handle_admin_metrics(event, dynamo_repo, model_counter, "corr-1")
        assert result["statusCode"] == 501


class TestHandleAdminRevenue:
    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_returns_current_revenue(self, populated_repo):
        from admin.metrics import handle_admin_revenue

        event = _make_admin_event(path="/admin/revenue")
        result = handle_admin_revenue(event, populated_repo, "corr-1")
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "current" in body
        assert body["current"]["activeSubscribers"] == 42

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_returns_historical_data(self, populated_repo):
        from admin.metrics import handle_admin_revenue

        event = _make_admin_event(path="/admin/revenue")
        result = handle_admin_revenue(event, populated_repo, "corr-1")
        body = json.loads(result["body"])
        assert "history" in body
        # Should have revenue fields from snapshots
        assert len(body["history"]) > 0

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_empty_revenue(self, dynamo_repo):
        from admin.metrics import handle_admin_revenue

        event = _make_admin_event(path="/admin/revenue")
        result = handle_admin_revenue(event, dynamo_repo, "corr-1")
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["current"] == {}

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_admin_auth_required(self, dynamo_repo):
        from admin.metrics import handle_admin_revenue

        event = _make_admin_event(path="/admin/revenue", groups=["editors"])
        result = handle_admin_revenue(event, dynamo_repo, "corr-1")
        assert result["statusCode"] == 403
