"""Tests for the daily snapshot Lambda handler."""

from __future__ import annotations

import importlib
import os
import time
from decimal import Decimal
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

TABLE_NAME = "pixel-prompt-users-snapshot"


@pytest.fixture
def wired(monkeypatch):
    """Set up DynamoDB table with test data for snapshot tests.

    Does NOT set AUTH_ENABLED to avoid contaminating config state for
    other test modules that share the same process.
    """
    monkeypatch.setenv("USERS_TABLE_NAME", TABLE_NAME)
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        try:
            ddb.create_table(
                TableName=TABLE_NAME,
                KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
        except Exception:
            # Table may already exist in the shared moto context
            pass
        try:
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        except Exception:
            pass
        # Clean any leftover items from previous test runs
        table = ddb.Table(TABLE_NAME)
        scan = table.scan()
        for item in scan.get("Items", []):
            table.delete_item(Key={"userId": item["userId"]})
        table = ddb.Table(TABLE_NAME)
        now = int(time.time())

        # Populate model counters
        for model in ("gemini", "nova", "openai", "firefly"):
            table.put_item(
                Item={
                    "userId": f"model#{model}",
                    "dailyCount": 100,
                    "dailyResetAt": now,
                    "updatedAt": now,
                }
            )

        # Populate some users
        table.put_item(
            Item={
                "userId": "user1",
                "tier": "free",
                "isSuspended": False,
                "createdAt": now,
                "updatedAt": now,
            }
        )
        table.put_item(
            Item={
                "userId": "user2",
                "tier": "paid",
                "isSuspended": False,
                "createdAt": now,
                "updatedAt": now,
            }
        )
        table.put_item(
            Item={
                "userId": "user3",
                "tier": "paid",
                "isSuspended": True,
                "createdAt": now,
                "updatedAt": now,
            }
        )

        # Populate revenue
        table.put_item(
            Item={
                "userId": "revenue#current",
                "activeSubscribers": 2,
                "monthlyChurn": 1,
                "updatedAt": now,
            }
        )

        from users.repository import UserRepository

        repo = UserRepository(TABLE_NAME, dynamodb_resource=ddb)
        yield repo, table


class TestHandleDailySnapshot:
    def test_creates_metrics_item(self, wired):
        repo, table = wired
        from ops.metrics import handle_daily_snapshot

        handle_daily_snapshot({}, None, repo=repo)
        # Check that a metrics item was created for today
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        item = table.get_item(Key={"userId": f"metrics#{today}"}).get("Item")
        assert item is not None
        assert "modelCounts" in item
        assert "usersByTier" in item
        assert "suspendedCount" in item
        assert "revenue" in item
        assert "createdAt" in item

    def test_model_counts_are_correct(self, wired):
        repo, table = wired
        from ops.metrics import handle_daily_snapshot

        handle_daily_snapshot({}, None, repo=repo)
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        item = table.get_item(Key={"userId": f"metrics#{today}"}).get("Item")
        model_counts = item["modelCounts"]
        assert model_counts["gemini"] == 100
        assert model_counts["nova"] == 100
        assert model_counts["openai"] == 100
        assert model_counts["firefly"] == 100

    def test_users_by_tier_counts(self, wired):
        repo, table = wired
        from ops.metrics import handle_daily_snapshot

        handle_daily_snapshot({}, None, repo=repo)
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        item = table.get_item(Key={"userId": f"metrics#{today}"}).get("Item")
        users_by_tier = item["usersByTier"]
        assert users_by_tier["free"] == 1
        assert users_by_tier["paid"] == 2

    def test_suspended_count(self, wired):
        repo, table = wired
        from ops.metrics import handle_daily_snapshot

        handle_daily_snapshot({}, None, repo=repo)
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        item = table.get_item(Key={"userId": f"metrics#{today}"}).get("Item")
        assert item["suspendedCount"] == 1

    def test_revenue_snapshot(self, wired):
        repo, table = wired
        from ops.metrics import handle_daily_snapshot

        handle_daily_snapshot({}, None, repo=repo)
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        item = table.get_item(Key={"userId": f"metrics#{today}"}).get("Item")
        revenue = item["revenue"]
        assert revenue["activeSubscribers"] == 2
        assert revenue["monthlyChurn"] == 1

    def test_idempotent_second_call(self, wired):
        repo, table = wired
        from ops.metrics import handle_daily_snapshot

        handle_daily_snapshot({}, None, repo=repo)
        # Second call should not overwrite
        # Modify the model counter to verify no overwrite
        now = int(time.time())
        table.update_item(
            Key={"userId": "model#gemini"},
            UpdateExpression="SET dailyCount = :c",
            ExpressionAttributeValues={":c": 999},
        )
        handle_daily_snapshot({}, None, repo=repo)
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        item = table.get_item(Key={"userId": f"metrics#{today}"}).get("Item")
        # Should still have original count (100), not 999
        assert item["modelCounts"]["gemini"] == 100

    def test_monthly_churn_reset_on_first_of_month(self, wired):
        repo, table = wired
        from ops.metrics import handle_daily_snapshot

        # Simulate running on day 1 of a month
        with patch("ops.metrics._today_str", return_value="2026-05-01"):
            with patch("ops.metrics._is_first_of_month", return_value=True):
                handle_daily_snapshot({}, None, repo=repo)
        # Check that monthlyChurn was reset
        revenue = table.get_item(Key={"userId": "revenue#current"}).get("Item")
        assert revenue.get("monthlyChurn", 0) == 0


class TestScheduledEventRouting:
    def test_lambda_handler_routes_snapshot_event(self, wired, monkeypatch):
        repo, table = wired
        import lambda_function

        # Patch _user_repo without reloading the module to avoid
        # contaminating config state for other test files.
        monkeypatch.setattr(lambda_function, "_user_repo", repo)

        event = {"source": "scheduled", "action": "daily_snapshot"}
        result = lambda_function.lambda_handler(event, None)
        assert result["statusCode"] == 200

        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        item = table.get_item(Key={"userId": f"metrics#{today}"}).get("Item")
        assert item is not None
