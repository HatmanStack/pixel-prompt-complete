"""Tests for account suspension: repository methods and quota enforcement."""

from __future__ import annotations

import importlib

import boto3
import pytest
from moto import mock_aws
from unittest.mock import patch

from users.repository import UserRepository

TABLE = "pixel-prompt-users"


@pytest.fixture
def users_table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield TABLE, ddb


def _repo(users_table):
    return UserRepository(users_table[0], dynamodb_resource=users_table[1])


def test_suspend_and_is_suspended(users_table):
    repo = _repo(users_table)
    repo.get_or_create_user("u1")
    repo.suspend_user("u1")
    assert repo.is_suspended("u1") is True


def test_unsuspend_clears_suspension(users_table):
    repo = _repo(users_table)
    repo.get_or_create_user("u1")
    repo.suspend_user("u1")
    assert repo.is_suspended("u1") is True
    repo.unsuspend_user("u1")
    assert repo.is_suspended("u1") is False


def test_is_suspended_returns_false_for_user_without_field(users_table):
    repo = _repo(users_table)
    repo.get_or_create_user("u1")
    assert repo.is_suspended("u1") is False


def test_is_suspended_returns_false_for_nonexistent_user(users_table):
    repo = _repo(users_table)
    assert repo.is_suspended("nonexistent") is False


def test_enforce_quota_blocks_suspended_free_user(users_table):
    from users.quota import enforce_quota
    from users.tier import TierContext

    repo = _repo(users_table)
    repo.get_or_create_user("u1")
    repo.suspend_user("u1")
    ctx = TierContext(
        tier="free",
        user_id="u1",
        email=None,
        is_authenticated=True,
        guest_token_id=None,
        issue_guest_cookie=False,
    )
    with patch("config.auth_enabled", True):
        result = enforce_quota(ctx, "generate", repo, 1_000_000)
    assert result.allowed is False
    assert result.reason == "suspended"


def test_enforce_quota_blocks_suspended_paid_user(users_table):
    from users.quota import enforce_quota
    from users.tier import TierContext

    repo = _repo(users_table)
    repo.get_or_create_user("u1")
    repo.set_tier("u1", "paid")
    repo.suspend_user("u1")
    ctx = TierContext(
        tier="paid",
        user_id="u1",
        email=None,
        is_authenticated=True,
        guest_token_id=None,
        issue_guest_cookie=False,
    )
    with patch("config.auth_enabled", True):
        result = enforce_quota(ctx, "generate", repo, 1_000_000)
    assert result.allowed is False
    assert result.reason == "suspended"


def test_enforce_quota_allows_unsuspended_user(users_table):
    from users.quota import enforce_quota
    from users.tier import TierContext

    repo = _repo(users_table)
    repo.get_or_create_user("u1")
    repo.suspend_user("u1")
    repo.unsuspend_user("u1")
    ctx = TierContext(
        tier="paid",
        user_id="u1",
        email=None,
        is_authenticated=True,
        guest_token_id=None,
        issue_guest_cookie=False,
    )
    with patch("config.auth_enabled", True):
        result = enforce_quota(ctx, "generate", repo, 1_000_000)
    assert result.allowed is True


def test_guest_tier_skips_suspension_check(users_table):
    from users.quota import enforce_quota
    from users.tier import TierContext

    repo = _repo(users_table)
    # Create guest item
    repo.upsert_guest("tok1", "iphash", 1_100_000)
    ctx = TierContext(
        tier="guest",
        user_id="guest#tok1",
        email=None,
        is_authenticated=False,
        guest_token_id="tok1",
        issue_guest_cookie=False,
    )
    with patch("config.auth_enabled", True):
        result = enforce_quota(ctx, "generate", repo, 1_000_000)
    # Guest should go through normal quota path, not be blocked by suspension
    assert result.allowed is True
