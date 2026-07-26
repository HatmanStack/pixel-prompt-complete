"""Tests that guest quota is bound to something the caller cannot choose.

A guest identity is a cookie. Before this, dropping it minted a fresh token
with a fresh counter, so the guest limit bounded nothing at all — an ipHash
was computed and stored on every guest record and then never read.
"""

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

TABLE_NAME = "pixel-prompt-users-guestip"
NOW = 1784980800


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "secret")
    import config

    importlib.reload(config)
    yield config
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.delenv("GUEST_TOKEN_SECRET", raising=False)
    importlib.reload(config)


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


def _guest(token_id, ip_hash="ip-aaa"):
    from users.tier import TierContext

    return TierContext(
        tier="guest",
        user_id=f"guest#{token_id}",
        email=None,
        is_authenticated=False,
        guest_token_id=token_id,
        issue_guest_cookie=False,
        ip_hash=ip_hash,
    )


def test_dropping_the_cookie_no_longer_resets_the_limit(auth_on, repo):
    """The whole point: a new token from the same IP hits the same ceiling."""
    from users.quota import enforce_quota

    limit = auth_on.guest_ip_generate_limit
    allowed = 0
    # Each request pretends to be a brand-new guest — i.e. cookie discarded.
    for i in range(limit + 5):
        repo.upsert_guest(f"tok{i}", "ip-aaa", NOW + 4000)
        result = enforce_quota(_guest(f"tok{i}"), "generate", repo, NOW)
        if result.allowed:
            allowed += 1
        else:
            assert result.reason == "guest_ip"

    assert allowed == limit, "a fresh cookie must not buy a fresh allowance"


def test_a_different_ip_gets_its_own_allowance(auth_on, repo, monkeypatch):
    """The bucket is per-IP, so one network cannot starve another.

    The global pool is raised here so the per-IP limit is the binding
    constraint; at shipped defaults the global cap would mask it.
    """
    import config

    monkeypatch.setattr(config, "guest_global_limit", 1000)
    from users.quota import enforce_quota

    limit = auth_on.guest_ip_generate_limit
    for i in range(limit):
        repo.upsert_guest(f"a{i}", "ip-aaa", NOW + 4000)
        enforce_quota(_guest(f"a{i}", "ip-aaa"), "generate", repo, NOW)

    assert enforce_quota(_guest("a-next", "ip-aaa"), "generate", repo, NOW).allowed is False

    repo.upsert_guest("b0", "ip-bbb", NOW + 4000)
    assert enforce_quota(_guest("b0", "ip-bbb"), "generate", repo, NOW).allowed is True


def test_per_ip_limit_binds_before_the_global_pool(auth_on):
    """Config coherence: an IP limit at or above the global cap is inert.

    The per-IP bucket exists to stop one caller draining the shared pool. If
    it is not strictly below the global limit, the global one always trips
    first and the per-IP check can never do anything.
    """
    assert auth_on.guest_ip_generate_limit < auth_on.guest_global_limit


def test_ip_window_expires(auth_on, repo):
    from users.quota import enforce_quota

    for i in range(auth_on.guest_ip_generate_limit):
        repo.upsert_guest(f"w{i}", "ip-ccc", NOW + 4000)
        enforce_quota(_guest(f"w{i}", "ip-ccc"), "generate", repo, NOW)
    assert enforce_quota(_guest("w-x", "ip-ccc"), "generate", repo, NOW).allowed is False

    later = NOW + auth_on.guest_ip_window_seconds + 1
    repo.upsert_guest("w-later", "ip-ccc", later + 4000)
    assert enforce_quota(_guest("w-later", "ip-ccc"), "generate", repo, later).allowed


def test_ip_limit_is_checked_before_the_global_pool(auth_on, repo):
    """A denied guest must not burn the shared global allowance."""
    from users.quota import enforce_quota

    for i in range(auth_on.guest_ip_generate_limit + 3):
        repo.upsert_guest(f"g{i}", "ip-ddd", NOW + 4000)
        enforce_quota(_guest(f"g{i}", "ip-ddd"), "generate", repo, NOW)

    global_item = repo.get_user("guest#__global__") or {}
    used = int(global_item.get("generateCount", 0) or 0)
    assert used <= auth_on.guest_ip_generate_limit


def test_missing_ip_hash_does_not_crash(auth_on, repo):
    """Absent source IP must degrade, not error."""
    from users.quota import enforce_quota
    from users.tier import TierContext

    repo.upsert_guest("no-ip", "unknown", NOW + 4000)
    ctx = TierContext(
        tier="guest",
        user_id="guest#no-ip",
        email=None,
        is_authenticated=False,
        guest_token_id="no-ip",
        issue_guest_cookie=False,
        ip_hash=None,
    )
    assert enforce_quota(ctx, "generate", repo, NOW).allowed is True


# ---- CAPTCHA ordering ----


def test_new_guest_row_is_not_written_during_resolution(auth_on, repo):
    """Identify, verify, then persist — not persist, then verify."""
    from auth.guest_token import GuestTokenService
    from users.tier import resolve_tier

    svc = GuestTokenService("secret")
    event = {
        "requestContext": {"http": {"sourceIp": "9.9.9.9", "method": "POST"}},
        "headers": {},
    }
    ctx = resolve_tier(event, repo, svc)

    assert ctx.tier == "guest"
    assert ctx.guest_row_pending is True
    assert repo.get_user(ctx.user_id) is None, "row written before CAPTCHA"


def test_persist_guest_writes_the_row(auth_on, repo):
    from auth.guest_token import GuestTokenService
    from users.tier import persist_guest, resolve_tier

    svc = GuestTokenService("secret")
    event = {
        "requestContext": {"http": {"sourceIp": "9.9.9.9", "method": "POST"}},
        "headers": {},
    }
    ctx = resolve_tier(event, repo, svc)
    persist_guest(ctx, repo)

    row = repo.get_user(ctx.user_id)
    assert row is not None
    assert row["ipHash"] == ctx.ip_hash


def test_persist_is_a_noop_for_an_existing_guest(auth_on, repo):
    from users.tier import persist_guest

    ctx = _guest("already-there")
    persist_guest(ctx, repo)
    assert repo.get_user("guest#already-there") is None


def test_resolved_guest_carries_an_ip_hash(auth_on, repo):
    """Quota cannot bind to what resolution does not surface."""
    from auth.guest_token import GuestTokenService
    from users.tier import resolve_tier

    svc = GuestTokenService("secret")
    event = {
        "requestContext": {"http": {"sourceIp": "1.2.3.4", "method": "POST"}},
        "headers": {},
    }
    ctx = resolve_tier(event, repo, svc)
    assert ctx.ip_hash
    assert len(ctx.ip_hash) == 16


def test_same_ip_hashes_consistently(auth_on, repo):
    from auth.guest_token import GuestTokenService
    from users.tier import resolve_tier

    svc = GuestTokenService("secret")

    def ctx_for(ip):
        return resolve_tier(
            {"requestContext": {"http": {"sourceIp": ip, "method": "POST"}}, "headers": {}},
            repo,
            svc,
        )

    assert ctx_for("5.5.5.5").ip_hash == ctx_for("5.5.5.5").ip_hash
    assert ctx_for("5.5.5.5").ip_hash != ctx_for("6.6.6.6").ip_hash


def test_one_abuser_cannot_drain_the_global_pool(auth_on, repo, monkeypatch):
    """The concrete failure the per-IP bucket prevents.

    Aggregate guest spend was already capped by GUEST_GLOBAL_LIMIT, so the
    honour-system hole was never unbounded cost — it was that a single caller
    cycling cookies could consume the entire shared allowance and deny every
    other guest.
    """
    from users.quota import enforce_quota

    # One caller, many cookies, same network.
    for i in range(auth_on.guest_global_limit + 10):
        repo.upsert_guest(f"abuse{i}", "ip-abuser", NOW + 4000)
        enforce_quota(_guest(f"abuse{i}", "ip-abuser"), "generate", repo, NOW)

    # A genuine guest on a different network can still get through.
    repo.upsert_guest("honest", "ip-honest", NOW + 4000)
    result = enforce_quota(_guest("honest", "ip-honest"), "generate", repo, NOW)
    assert result.allowed is True, "one abuser locked out everyone else"
