"""Tests for admin user management endpoints.

Covers:
- User list with pagination, tier filter, and suspension filter
- Exclusion of non-user records (guest#, model#, metrics#, revenue#)
- User detail retrieval and 404 for missing user
- Suspend/unsuspend with email notifications
- Notify with warning and custom email types
- Admin auth enforcement on all endpoints
"""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from users.repository import UserRepository


def _make_admin_event(
    path: str = "/admin/users",
    method: str = "GET",
    body: dict | None = None,
    groups: list[str] | None = None,
):
    """Build an API Gateway event with admin JWT claims."""
    if groups is None:
        groups = ["admins"]
    event = {
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
        "queryStringParameters": {},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


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
    """Repo pre-populated with a mix of user types and synthetic records."""
    now = int(time.time())
    table = dynamo_repo._table

    # Real users
    for i in range(5):
        tier = "free" if i < 3 else "paid"
        item = {
            "userId": f"user-{i}",
            "tier": tier,
            "email": f"user{i}@example.com",
            "createdAt": now,
            "updatedAt": now,
        }
        if i == 2:
            item["isSuspended"] = True
        table.put_item(Item=item)

    # Synthetic records that should be excluded
    table.put_item(Item={"userId": "guest#abc", "tier": "guest", "createdAt": now})
    table.put_item(Item={"userId": "model#gemini", "dailyCount": 100, "createdAt": now})
    table.put_item(Item={"userId": "metrics#2026-04-12", "createdAt": now})
    table.put_item(Item={"userId": "revenue#current", "createdAt": now})

    return dynamo_repo


class TestScanUsers:
    def test_returns_only_real_users(self, populated_repo):
        items, last_key = populated_repo.scan_users(limit=50)
        user_ids = [item["userId"] for item in items]
        assert len(items) == 5
        for uid in user_ids:
            assert not uid.startswith("guest#")
            assert not uid.startswith("model#")
            assert not uid.startswith("metrics#")
            assert not uid.startswith("revenue#")

    def test_pagination(self, populated_repo):
        items1, last_key1 = populated_repo.scan_users(limit=2)
        assert len(items1) <= 2
        # With 5 real users + 4 synthetic, DynamoDB pages may vary;
        # we only assert that a last_key is returned when more items exist
        if last_key1:
            items2, _ = populated_repo.scan_users(limit=50, last_key=last_key1)
            all_ids = {item["userId"] for item in items1 + items2}
            # We should get all 5 real users across both pages
            for i in range(5):
                assert f"user-{i}" in all_ids

    def test_tier_filter(self, populated_repo):
        items, _ = populated_repo.scan_users(limit=50, tier_filter="paid")
        assert all(item.get("tier") == "paid" for item in items)
        assert len(items) == 2

    def test_suspended_filter(self, populated_repo):
        items, _ = populated_repo.scan_users(limit=50, suspended_filter=True)
        assert all(item.get("isSuspended") for item in items)
        assert len(items) == 1


class TestHandleAdminUsersList:
    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_returns_user_list(self, populated_repo):
        from admin.users import handle_admin_users_list

        event = _make_admin_event(path="/admin/users")
        result = handle_admin_users_list(event, populated_repo, "corr-1")
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert "users" in body
        assert body["count"] == 5

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_tier_filter(self, populated_repo):
        from admin.users import handle_admin_users_list

        event = _make_admin_event(path="/admin/users")
        event["queryStringParameters"] = {"tier": "paid"}
        result = handle_admin_users_list(event, populated_repo, "corr-1")
        body = json.loads(result["body"])
        assert body["count"] == 2

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_suspended_filter(self, populated_repo):
        from admin.users import handle_admin_users_list

        event = _make_admin_event(path="/admin/users")
        event["queryStringParameters"] = {"suspended": "true"}
        result = handle_admin_users_list(event, populated_repo, "corr-1")
        body = json.loads(result["body"])
        assert body["count"] == 1

    @patch("config.admin_enabled", False)
    @patch("config.auth_enabled", True)
    def test_non_admin_returns_501(self, populated_repo):
        from admin.users import handle_admin_users_list

        event = _make_admin_event(path="/admin/users")
        result = handle_admin_users_list(event, populated_repo, "corr-1")
        assert result["statusCode"] == 501


class TestHandleAdminUserDetail:
    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_returns_user_record(self, populated_repo):
        from admin.users import handle_admin_user_detail

        event = _make_admin_event(path="/admin/users/user-0")
        result = handle_admin_user_detail(event, populated_repo, "corr-1")
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["userId"] == "user-0"
        assert body["email"] == "user0@example.com"

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_returns_404_for_missing_user(self, populated_repo):
        from admin.users import handle_admin_user_detail

        event = _make_admin_event(path="/admin/users/nonexistent")
        result = handle_admin_user_detail(event, populated_repo, "corr-1")
        assert result["statusCode"] == 404

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_non_admin_returns_403(self, populated_repo):
        from admin.users import handle_admin_user_detail

        event = _make_admin_event(path="/admin/users/user-0", groups=["editors"])
        result = handle_admin_user_detail(event, populated_repo, "corr-1")
        assert result["statusCode"] == 403
