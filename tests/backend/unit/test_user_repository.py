"""Tests for users.repository.UserRepository using moto."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

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


def test_get_or_create_user(users_table):
    repo = _repo(users_table)
    first = repo.get_or_create_user("u1", email="u@example.com")
    assert first["userId"] == "u1"
    assert first["tier"] == "free"
    second = repo.get_or_create_user("u1")
    assert second["userId"] == "u1"


def test_increment_generate_within_window(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    ok1, item1 = repo.increment_generate("u1", 3600, 5, now)
    ok2, item2 = repo.increment_generate("u1", 3600, 5, now + 10)
    assert ok1 and ok2
    assert int(item2["generateCount"]) == 2


def test_increment_generate_limit_block(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    ok, _ = repo.increment_generate("u1", 3600, 1, now)
    assert ok
    ok2, item = repo.increment_generate("u1", 3600, 1, now + 5)
    assert not ok2
    assert int(item["generateCount"]) == 1


def test_increment_generate_resets_window(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    repo.increment_generate("u1", 3600, 1, now)
    # Advance past window.
    later = now + 4000
    ok, item = repo.increment_generate("u1", 3600, 1, later)
    assert ok
    assert int(item["generateCount"]) == 1
    assert int(item["windowStart"]) >= later - 1


def test_increment_refine_independent_of_generate(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    repo.increment_generate("u1", 3600, 5, now)
    ok, item = repo.increment_refine("u1", 3600, 5, now)
    assert ok
    assert int(item["refineCount"]) == 1
    assert int(item["generateCount"]) == 1


def test_increment_daily(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    repo.get_or_create_user("u1")
    ok, item = repo.increment_daily("u1", 86400, 3, now)
    assert ok
    assert int(item["dailyCount"]) == 1


def test_set_tier_paid_and_free(users_table):
    repo = _repo(users_table)
    repo.get_or_create_user("u1")
    repo.set_tier("u1", "paid", stripeSubscriptionId="sub_1", subscriptionStatus="active")
    item = repo.get_user("u1")
    assert item["tier"] == "paid"
    assert item["stripeSubscriptionId"] == "sub_1"
    repo.set_tier("u1", "free")
    assert repo.get_user("u1")["tier"] == "free"


def test_set_stripe_customer_id_idempotent(users_table):
    repo = _repo(users_table)
    repo.get_or_create_user("u1")
    repo.set_stripe_customer_id("u1", "cus_1")
    repo.set_stripe_customer_id("u1", "cus_1")
    assert repo.get_user("u1")["stripeCustomerId"] == "cus_1"


def test_guest_item_uses_ttl(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    item = repo.upsert_guest("tok1", "iphash", now + 3900)
    assert item["userId"] == "guest#tok1"
    assert int(item["ttl"]) == now + 3900


def test_increment_guest_generate(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    repo.upsert_guest("tok1", "ip", now + 3900)
    ok, _ = repo.increment_guest_generate("tok1", 1, 3600, now)
    assert ok
    ok2, _ = repo.increment_guest_generate("tok1", 1, 3600, now + 1)
    assert not ok2


def test_global_guest_counter_atomic(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    for _ in range(3):
        ok, _ = repo.increment_global_guest(5, 3600, now)
        assert ok
    # 4 more, should block after 5.
    results = [repo.increment_global_guest(5, 3600, now)[0] for _ in range(4)]
    assert results.count(True) == 2
    assert results.count(False) == 2


def test_touch_quota_window_resets(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    repo.increment_generate("u1", 3600, 5, now)
    # After window expiry, touch should zero counters.
    later = now + 4000
    item = repo.touch_quota_window("u1", 3600, later)
    assert int(item["generateCount"]) == 0
    assert int(item["windowStart"]) >= later - 1
