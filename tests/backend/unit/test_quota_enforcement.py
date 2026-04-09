"""Tests for users.quota.enforce_quota."""

from __future__ import annotations

import importlib

import boto3
import pytest
from moto import mock_aws

from users.tier import TierContext


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("FREE_GENERATE_LIMIT", "1")
    monkeypatch.setenv("FREE_REFINE_LIMIT", "2")
    monkeypatch.setenv("GUEST_GENERATE_LIMIT", "1")
    monkeypatch.setenv("GUEST_GLOBAL_LIMIT", "5")
    monkeypatch.setenv("PAID_DAILY_LIMIT", "3")
    import config
    importlib.reload(config)
    yield
    for v in (
        "AUTH_ENABLED",
        "FREE_GENERATE_LIMIT",
        "FREE_REFINE_LIMIT",
        "GUEST_GENERATE_LIMIT",
        "GUEST_GLOBAL_LIMIT",
        "PAID_DAILY_LIMIT",
    ):
        monkeypatch.delenv(v, raising=False)
    importlib.reload(config)


@pytest.fixture
def repo(env):
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="t",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        from users.repository import UserRepository
        yield UserRepository("t", dynamodb_resource=ddb)


def _guest_ctx(tok="tok1"):
    return TierContext(
        tier="guest",
        user_id=f"guest#{tok}",
        email=None,
        is_authenticated=False,
        guest_token_id=tok,
        issue_guest_cookie=False,
    )


def _user_ctx(tier="free", uid="u1"):
    return TierContext(
        tier=tier,
        user_id=uid,
        email=None,
        is_authenticated=True,
        guest_token_id=None,
        issue_guest_cookie=False,
    )


def test_flags_off_always_allowed(monkeypatch):
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    import config
    importlib.reload(config)
    from users.quota import enforce_quota
    r = enforce_quota(_user_ctx(), "generate", repo=None, now=0)
    assert r.allowed


def test_guest_refine_blocked(repo):
    from users.quota import enforce_quota
    r = enforce_quota(_guest_ctx(), "refine", repo, now=1000)
    assert not r.allowed
    assert r.reason == "guest_per_user"


def test_guest_generate_allowed_once(repo):
    from users.quota import enforce_quota
    repo.upsert_guest("tok1", "ip", 9999)
    r1 = enforce_quota(_guest_ctx(), "generate", repo, now=1000)
    r2 = enforce_quota(_guest_ctx(), "generate", repo, now=1001)
    assert r1.allowed
    assert not r2.allowed
    assert r2.reason == "guest_per_user"


def test_guest_global_cap_blocks_before_per_user(repo):
    from users.quota import enforce_quota
    # 5 different guests, 5 calls consumed globally.
    for i in range(5):
        repo.upsert_guest(f"g{i}", "ip", 9999)
        ctx = _guest_ctx(f"g{i}")
        r = enforce_quota(ctx, "generate", repo, now=1000)
        assert r.allowed, i
    # New guest blocked by global cap.
    repo.upsert_guest("g5", "ip", 9999)
    r = enforce_quota(_guest_ctx("g5"), "generate", repo, now=1000)
    assert not r.allowed
    assert r.reason == "guest_global"


def test_free_generate_limit(repo):
    from users.quota import enforce_quota
    r1 = enforce_quota(_user_ctx(), "generate", repo, now=1000)
    r2 = enforce_quota(_user_ctx(), "generate", repo, now=1001)
    assert r1.allowed
    assert not r2.allowed
    assert r2.reason == "free_generate"


def test_free_refine_limit(repo):
    from users.quota import enforce_quota
    r1 = enforce_quota(_user_ctx(), "refine", repo, now=1000)
    r2 = enforce_quota(_user_ctx(), "refine", repo, now=1001)
    r3 = enforce_quota(_user_ctx(), "refine", repo, now=1002)
    assert r1.allowed and r2.allowed
    assert not r3.allowed
    assert r3.reason == "free_refine"


def test_paid_generate_unlimited(repo):
    from users.quota import enforce_quota
    for i in range(10):
        r = enforce_quota(_user_ctx(tier="paid", uid="p1"), "generate", repo, now=1000 + i)
        assert r.allowed


def test_paid_daily_refine_limit(repo):
    from users.quota import enforce_quota
    repo.get_or_create_user("p1")
    results = [
        enforce_quota(_user_ctx(tier="paid", uid="p1"), "refine", repo, now=1000 + i).allowed
        for i in range(5)
    ]
    assert results.count(True) == 3
    assert results.count(False) == 2
