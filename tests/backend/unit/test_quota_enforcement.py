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
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "test-secret")
    monkeypatch.setenv("FREE_GENERATE_LIMIT", "1")
    monkeypatch.setenv("FREE_REFINE_LIMIT", "2")
    monkeypatch.setenv("GUEST_GENERATE_LIMIT", "1")
    monkeypatch.setenv("GUEST_GLOBAL_LIMIT", "5")
    monkeypatch.setenv("PAID_DAILY_LIMIT", "3")
    monkeypatch.setenv("PAID_DAILY_GENERATE_LIMIT", "2")
    import config
    importlib.reload(config)
    yield
    for v in (
        "GUEST_TOKEN_SECRET",
        "FREE_GENERATE_LIMIT",
        "FREE_REFINE_LIMIT",
        "GUEST_GENERATE_LIMIT",
        "GUEST_GLOBAL_LIMIT",
        "PAID_DAILY_LIMIT",
        "PAID_DAILY_GENERATE_LIMIT",
    ):
        monkeypatch.delenv(v, raising=False)
    # AUTH_ENABLED is set, not cleared: it has no default, so reloading
    # without it raises.
    monkeypatch.setenv("AUTH_ENABLED", "false")
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


def test_flags_off_still_meters_anonymous_callers(monkeypatch, repo):
    """Auth off no longer means unlimited.

    Auth answers "who is this"; quota answers "how much may they have".
    Conflating them made an open deployment an unlimited one. An
    unauthenticated caller is now metered against their source IP.
    """
    monkeypatch.setenv("AUTH_ENABLED", "false")
    import config

    importlib.reload(config)
    from users.quota import enforce_quota
    from users.tier import TierContext

    ctx = TierContext(
        tier="anon",
        user_id="anon#deadbeef",
        email=None,
        is_authenticated=False,
        guest_token_id=None,
        issue_guest_cookie=False,
        ip_hash="deadbeef",
    )

    allowed = 0
    for _ in range(config.anon_generate_limit + 3):
        if enforce_quota(ctx, "generate", repo, now=1000).allowed:
            allowed += 1
    assert allowed == config.anon_generate_limit

    denied = enforce_quota(ctx, "generate", repo, now=1000)
    assert denied.allowed is False
    assert denied.reason == "anon_generate"


def test_anon_quota_fails_open_if_the_store_is_unreachable(monkeypatch):
    """A broken counter store must not 500 every request.

    Same reasoning as the spend ceiling: an unreachable counter is not
    evidence the caller is over limit.
    """
    monkeypatch.setenv("AUTH_ENABLED", "false")
    import config

    importlib.reload(config)
    from unittest.mock import MagicMock

    from users.quota import enforce_quota
    from users.tier import TierContext

    broken = MagicMock()
    broken.increment_anon.side_effect = RuntimeError("dynamo down")
    ctx = TierContext(
        tier="anon",
        user_id="anon#x",
        email=None,
        is_authenticated=False,
        guest_token_id=None,
        issue_guest_cookie=False,
        ip_hash="x",
    )
    assert enforce_quota(ctx, "generate", broken, now=0).allowed is True


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


def test_paid_generate_is_bounded(repo):
    """Was unlimited. Four providers per call makes it the priciest operation
    in the product, and it was bounded only by ceilings shared across every
    user, so one account could consume the organisation's whole day."""
    from users.quota import enforce_quota
    results = [
        enforce_quota(_user_ctx(tier="paid", uid="p1"), "generate", repo, now=1000 + i)
        for i in range(4)
    ]
    assert [r.allowed for r in results] == [True, True, False, False]
    assert results[-1].reason == "paid_daily_generate"


def test_paid_generate_and_refine_are_separate_counters(repo):
    """They are priced differently everywhere else; one bucket would make a
    generation cost the same as a refinement."""
    from users.quota import enforce_quota
    for i in range(2):
        assert enforce_quota(
            _user_ctx(tier="paid", uid="p1"), "generate", repo, now=1000 + i
        ).allowed
    # Generate is now exhausted (limit 2). Refine has its own limit of 3.
    assert not enforce_quota(
        _user_ctx(tier="paid", uid="p1"), "generate", repo, now=1010
    ).allowed
    for i in range(3):
        assert enforce_quota(
            _user_ctx(tier="paid", uid="p1"), "refine", repo, now=1020 + i
        ).allowed


def test_paid_refine_exhaustion_does_not_bind_generate(repo):
    from users.quota import enforce_quota
    for i in range(3):
        enforce_quota(_user_ctx(tier="paid", uid="p1"), "refine", repo, now=1000 + i)
    assert not enforce_quota(
        _user_ctx(tier="paid", uid="p1"), "refine", repo, now=1010
    ).allowed
    assert enforce_quota(
        _user_ctx(tier="paid", uid="p1"), "generate", repo, now=1011
    ).allowed


def test_both_daily_counters_zero_together_when_the_window_goes_stale(repo):
    """They share dailyResetAt. If only one is zeroed on reset, the other is
    stranded at its limit for as long as the account stays active."""
    from users.quota import enforce_quota
    enforce_quota(_user_ctx(tier="paid", uid="p1"), "generate", repo, now=1000)
    enforce_quota(_user_ctx(tier="paid", uid="p1"), "generate", repo, now=1001)
    enforce_quota(_user_ctx(tier="paid", uid="p1"), "refine", repo, now=1002)
    item = repo.get_user("p1")
    assert int(item["dailyGenerateCount"]) == 2
    assert int(item["dailyCount"]) == 1

    later = 1000 + 86401
    assert enforce_quota(
        _user_ctx(tier="paid", uid="p1"), "generate", repo, now=later
    ).allowed
    item = repo.get_user("p1")
    assert int(item["dailyGenerateCount"]) == 1, "the new window should start at one"
    assert int(item["dailyCount"]) == 0, "the sibling counter did not reset with it"


def test_paid_daily_refine_limit(repo):
    from users.quota import enforce_quota
    repo.get_or_create_user("p1")
    results = [
        enforce_quota(_user_ctx(tier="paid", uid="p1"), "refine", repo, now=1000 + i).allowed
        for i in range(5)
    ]
    assert results.count(True) == 3
    assert results.count(False) == 2


def test_a_guest_context_without_a_token_id_is_denied_not_asserted(repo, caplog):
    """Was a bare `assert ctx.guest_token_id is not None`.

    Under `python -O` the check vanishes entirely and an unidentifiable guest
    is metered against nothing, which is how a guest bucket becomes unlimited.
    Without -O it raised AssertionError with no diagnostic, inside a fail-open
    wrapper, in a function whose every other failure returns a QuotaResult.

    Denying rather than failing open is deliberate: reaching this line means
    resolve_tier produced a guest context with no token id, which is a bug.
    """
    from users.quota import enforce_quota
    from users.tier import TierContext

    ctx = TierContext(
        tier="guest",
        user_id="guest#unknown",
        email=None,
        is_authenticated=False,
        guest_token_id=None,
        issue_guest_cookie=False,
    )

    with caplog.at_level("ERROR"):
        result = enforce_quota(ctx, "generate", repo, now=1000)

    assert result.allowed is False
    assert result.reason == "guest_identity_missing"
    assert result.reset_at == 0
    assert any("guest" in r.getMessage().lower() for r in caplog.records), (
        "a bug-shaped denial has to be alarmable"
    )


def test_the_quota_module_has_no_bare_asserts():
    """`python -O` strips them, and a stripped check is not a check."""
    import inspect

    import users.quota as quota_module

    source = inspect.getsource(quota_module)
    assert "assert " not in source


def test_a_guest_with_no_token_id_burns_no_per_ip_slot():
    """The denial must come BEFORE the per-IP bucket is charged.

    The per-IP bucket is the only guest counter a caller cannot reset:
    dropping the cookie mints a fresh token with a fresh per-token count, but
    the IP hash persists. Charging it and then refusing the request spends an
    allowance the caller has no way to recover, for a request that was never
    going to be served -- and the branch exists precisely for a bug upstream
    in resolve_tier, so the caller did nothing to earn it.
    """
    from unittest.mock import MagicMock

    from users.quota import enforce_quota
    from users.tier import TierContext

    repo = MagicMock()
    ctx = TierContext(
        tier="guest",
        user_id="guest#unknown",
        email=None,
        is_authenticated=False,
        guest_token_id=None,
        issue_guest_cookie=False,
        ip_hash="deadbeef",
    )

    result = enforce_quota(ctx, "generate", repo, now=1000)

    assert result.allowed is False
    assert result.reason == "guest_identity_missing"
    assert repo.increment_guest_ip.call_count == 0, (
        "a slot was consumed from the one bucket the caller cannot reset, "
        "for a request that was refused anyway"
    )
    assert repo.increment_guest_generate.call_count == 0
