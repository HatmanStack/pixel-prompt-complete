"""Tests for revenue tracking counters in UserRepository."""

from __future__ import annotations

import importlib
import os

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

TABLE_NAME = "pixel-prompt-users-revenue"


@pytest.fixture
def repo():
    """Create a UserRepository with a mocked DynamoDB table."""
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


class TestIncrementRevenueCounter:
    def test_creates_item_on_first_call(self, repo):
        repo.increment_revenue_counter("activeSubscribers", 1)
        item = repo.get_user("revenue#current")
        assert item is not None
        assert item["activeSubscribers"] == 1
        assert "updatedAt" in item

    def test_increments_on_subsequent_calls(self, repo):
        repo.increment_revenue_counter("activeSubscribers", 1)
        repo.increment_revenue_counter("activeSubscribers", 1)
        repo.increment_revenue_counter("activeSubscribers", 1)
        item = repo.get_user("revenue#current")
        assert item["activeSubscribers"] == 3

    def test_increments_different_fields(self, repo):
        repo.increment_revenue_counter("activeSubscribers", 1)
        repo.increment_revenue_counter("monthlyChurn", 1)
        item = repo.get_user("revenue#current")
        assert item["activeSubscribers"] == 1
        assert item["monthlyChurn"] == 1


class TestDecrementRevenueCounter:
    def test_decrements_counter(self, repo):
        repo.increment_revenue_counter("activeSubscribers", 5)
        repo.decrement_revenue_counter("activeSubscribers", 2)
        item = repo.get_user("revenue#current")
        assert item["activeSubscribers"] == 3

    def test_decrement_creates_item_if_missing(self, repo):
        repo.decrement_revenue_counter("activeSubscribers", 1)
        item = repo.get_user("revenue#current")
        assert item is not None
        # DynamoDB ADD with -1 on a missing attribute starts at -1
        assert item["activeSubscribers"] == -1


class TestGetRevenue:
    def test_returns_empty_dict_when_no_item(self, repo):
        result = repo.get_revenue()
        assert result == {}

    def test_returns_current_counters(self, repo):
        repo.increment_revenue_counter("activeSubscribers", 10)
        repo.increment_revenue_counter("monthlyChurn", 2)
        result = repo.get_revenue()
        assert result["activeSubscribers"] == 10
        assert result["monthlyChurn"] == 2
        assert result["userId"] == "revenue#current"
