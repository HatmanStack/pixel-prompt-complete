"""Tests for the credit ledger.

Replaces call-counting quota with a debited balance. These verify the
properties that are verifiable here: the right write path is taken, its
condition is correct, allotments renew on the right boundary (Stripe's for
paid, a fixed window for free), and the whole thing stays off until
CREDITS_ENABLED is set.

Not verifiable here: no-overdraw under concurrency. That is DynamoDB's
guarantee that a ConditionExpression and its update are evaluated as one
operation, and moto does not honour it — raw boto3 against moto, with no
project code involved, will let a conditional ``bal >= :amt`` decrement drive
a balance negative under thread contention. A threaded test would therefore
be flaky and prove nothing about production, so the conditions are tested
directly instead.
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

TABLE_NAME = "pixel-prompt-users-credits"
NOW = 1784980800  # 2026-07-25T12:00:00Z


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


def _ctx(tier="paid", user_id="u1"):
    from users.tier import TierContext

    return TierContext(
        tier=tier,
        user_id=user_id,
        email=None,
        is_authenticated=True,
        guest_token_id=None,
        issue_guest_cookie=False,
    )


# ---- Repository primitive ----


def test_first_debit_grants_the_allotment(repo):
    ok, item = repo.debit_credits(
        "u1", amount=100, allotment=6500, period_end=NOW + 86400, now=NOW
    )
    assert ok
    assert int(item["creditsRemaining"]) == 6400
    assert int(item["creditPeriodEnd"]) == NOW + 86400


def test_debits_accumulate(repo):
    for _ in range(4):
        repo.debit_credits(
            "u1", amount=100, allotment=500, period_end=NOW + 86400, now=NOW
        )
    assert repo.get_credit_balance("u1")["creditsRemaining"] == 100


def test_debit_denied_when_balance_insufficient(repo):
    repo.debit_credits("u1", amount=100, allotment=100, period_end=NOW + 86400, now=NOW)
    ok, item = repo.debit_credits(
        "u1", amount=100, allotment=100, period_end=NOW + 86400, now=NOW
    )
    assert ok is False
    assert int(item["creditsRemaining"]) == 0


def test_renewal_grants_exactly_one_allotment(repo):
    """The renewal write moves the period forward, so only one caller wins it.

    NOTE ON CONCURRENCY: the no-overdraw guarantee comes from DynamoDB
    evaluating a ConditionExpression and its update as one operation. That
    cannot be verified here — moto is not thread-safe. Raw boto3 against moto,
    with no project code involved, will happily let a conditional
    ``bal >= :amt`` decrement drive a balance negative under thread contention.
    A threaded test against moto therefore proves nothing about production and
    only produces a flaky suite. These tests verify the conditions instead;
    atomicity is DynamoDB's contract.
    """
    ok1, item1 = repo.debit_credits(
        "u", amount=100, allotment=1000, period_end=NOW + 86400, now=NOW
    )
    ok2, item2 = repo.debit_credits(
        "u", amount=100, allotment=1000, period_end=NOW + 86400, now=NOW
    )
    assert ok1 and ok2
    # Second call took the steady-state path, not a second grant.
    assert int(item1["creditsRemaining"]) == 900
    assert int(item2["creditsRemaining"]) == 800


def test_steady_state_debit_requires_a_current_period(repo):
    """A debit must not succeed against a lapsed period's leftover balance.

    Without the ``creditPeriodEnd > :now`` guard, the steady-state write would
    happily spend credits belonging to a window that has already closed.
    """
    repo.debit_credits("u", amount=100, allotment=1000, period_end=NOW + 10, now=NOW)
    assert repo.get_credit_balance("u")["creditsRemaining"] == 900

    # Well past the period end, with a fresh window supplied.
    later = NOW + 11
    ok, item = repo.debit_credits(
        "u", amount=100, allotment=1000, period_end=later + 86400, now=later
    )
    assert ok
    # Renewed rather than continuing to spend the old balance.
    assert int(item["creditsRemaining"]) == 900
    assert int(item["creditPeriodEnd"]) == later + 86400


def test_cost_above_allotment_is_denied_without_writing_negative(repo):
    """A charge no allotment could cover must deny, not grant a negative balance."""
    ok, _ = repo.debit_credits(
        "u_big", amount=5000, allotment=1000, period_end=NOW + 86400, now=NOW
    )
    assert ok is False
    assert repo.get_credit_balance("u_big")["creditsRemaining"] >= 0


def test_period_rollover_grants_fresh_allotment(repo):
    repo.debit_credits("u1", amount=500, allotment=500, period_end=NOW + 100, now=NOW)
    assert repo.get_credit_balance("u1")["creditsRemaining"] == 0

    later = NOW + 101
    ok, item = repo.debit_credits(
        "u1", amount=100, allotment=500, period_end=later + 86400, now=later
    )
    assert ok
    assert int(item["creditsRemaining"]) == 400


def test_period_not_reset_early(repo):
    repo.debit_credits("u1", amount=500, allotment=500, period_end=NOW + 86400, now=NOW)
    ok, _ = repo.debit_credits(
        "u1", amount=100, allotment=500, period_end=NOW + 86400, now=NOW + 100
    )
    assert ok is False, "allotment must not refresh mid-period"


def test_rollover_does_not_stack_allotments(repo):
    """Crossing a period boundary grants one allotment, not one per request."""
    repo.debit_credits("u_roll", amount=500, allotment=500, period_end=NOW + 10, now=NOW)
    assert repo.get_credit_balance("u_roll")["creditsRemaining"] == 0

    later = NOW + 11
    for _ in range(5):
        repo.debit_credits(
            "u_roll", amount=100, allotment=500, period_end=later + 86400, now=later
        )
    # Exactly one allotment of 500 was granted and then fully spent.
    assert repo.get_credit_balance("u_roll")["creditsRemaining"] == 0
    ok, _ = repo.debit_credits(
        "u_roll", amount=100, allotment=500, period_end=later + 86400, now=later
    )
    assert ok is False


def test_zero_cost_never_debits(repo):
    ok, _ = repo.debit_credits(
        "u1", amount=0, allotment=500, period_end=NOW + 86400, now=NOW
    )
    assert ok is True


def test_grant_credits_tops_up(repo):
    repo.debit_credits("u1", amount=100, allotment=500, period_end=NOW + 86400, now=NOW)
    repo.grant_credits("u1", 250, now=NOW)
    assert repo.get_credit_balance("u1")["creditsRemaining"] == 650


# ---- Quota integration ----


@pytest.fixture
def credits_on(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "secret")
    monkeypatch.setenv("CREDITS_ENABLED", "true")
    import config

    importlib.reload(config)
    yield config
    monkeypatch.delenv("CREDITS_ENABLED", raising=False)
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.delenv("GUEST_TOKEN_SECRET", raising=False)
    importlib.reload(config)


def test_generate_costs_four_times_a_refine(credits_on, repo):
    """The 4x gap is the reason credits exist rather than call counts."""
    from users.quota import enforce_quota

    gen = enforce_quota(_ctx("paid", "u_gen"), "generate", repo, NOW)
    ref = enforce_quota(_ctx("paid", "u_ref"), "refine", repo, NOW)
    assert gen.usage["creditsCharged"] == 4 * ref.usage["creditsCharged"]


def test_paid_generate_is_no_longer_unlimited(credits_on, repo):
    """quota.py used to return an unconditional allow here."""
    from users.quota import enforce_quota

    allotment = credits_on.paid_monthly_credits
    per_call = credits_on.credits_per_generate
    calls = allotment // per_call

    for _ in range(calls):
        assert enforce_quota(_ctx("paid"), "generate", repo, NOW).allowed

    denied = enforce_quota(_ctx("paid"), "generate", repo, NOW)
    assert denied.allowed is False
    assert denied.reason == "insufficient_credits"


def test_free_tier_is_bounded_by_a_monthly_budget(credits_on, repo):
    """Free was a rolling 1-hour rate limit: ~720 generates/month, unbounded spend."""
    from users.quota import enforce_quota

    calls = credits_on.free_monthly_credits // credits_on.credits_per_generate
    for _ in range(calls):
        assert enforce_quota(_ctx("free", "u_free"), "generate", repo, NOW).allowed

    # An hour later the old rate limit would have reset. The budget does not.
    later = enforce_quota(_ctx("free", "u_free"), "generate", repo, NOW + 3600)
    assert later.allowed is False
    assert later.reason == "insufficient_credits"


def test_usage_reports_remaining_balance(credits_on, repo):
    from users.quota import enforce_quota

    result = enforce_quota(_ctx("paid"), "generate", repo, NOW)
    assert result.usage["creditsRemaining"] == (
        credits_on.paid_monthly_credits - credits_on.credits_per_generate
    )
    assert result.usage["creditsAllotment"] == credits_on.paid_monthly_credits


def test_paid_period_follows_stripe_boundary(credits_on, repo):
    """Not a fixed 30-day clock: Stripe cycles run 28-31 days."""
    from users.quota import enforce_quota

    stripe_end = NOW + (31 * 86400)
    repo.get_or_create_user("u_stripe")
    repo.set_tier("u_stripe", "paid", stripeCurrentPeriodEnd=stripe_end)

    result = enforce_quota(_ctx("paid", "u_stripe"), "generate", repo, NOW)
    assert result.allowed
    assert result.reset_at == stripe_end


def test_paid_falls_back_when_stripe_period_missing(credits_on, repo):
    """A paying customer must never be stuck at zero because a webhook was missed."""
    from users.quota import enforce_quota

    result = enforce_quota(_ctx("paid", "u_nostripe"), "generate", repo, NOW)
    assert result.allowed
    assert result.reset_at == NOW + credits_on.paid_credit_fallback_period_seconds


def test_stale_stripe_period_is_not_used(credits_on, repo):
    from users.quota import enforce_quota

    repo.get_or_create_user("u_stale")
    repo.set_tier("u_stale", "paid", stripeCurrentPeriodEnd=NOW - 100)
    result = enforce_quota(_ctx("paid", "u_stale"), "generate", repo, NOW)
    assert result.allowed
    assert result.reset_at > NOW


def test_free_period_uses_fixed_window(credits_on, repo):
    from users.quota import enforce_quota

    result = enforce_quota(_ctx("free", "u_f"), "generate", repo, NOW)
    assert result.reset_at == NOW + credits_on.free_credit_period_seconds


def test_guests_stay_on_legacy_limits(credits_on, repo):
    """A guest credit balance would bound nothing: drop the cookie, get a new one."""
    from users.quota import enforce_quota

    result = enforce_quota(_ctx("guest", "guest#abc"), "refine", repo, NOW)
    assert result.reason == "guest_per_user"
    assert "creditsRemaining" not in result.usage


def test_suspended_user_blocked_before_any_debit(credits_on, repo):
    from users.quota import enforce_quota

    repo.get_or_create_user("u_susp")
    repo.suspend_user("u_susp")
    result = enforce_quota(_ctx("paid", "u_susp"), "generate", repo, NOW)
    assert result.allowed is False
    assert result.reason == "suspended"
    assert repo.get_credit_balance("u_susp")["creditsRemaining"] == 0


def test_ledger_is_off_by_default(repo, monkeypatch):
    """CREDITS_ENABLED gates the whole thing so it can roll back without a deploy."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "secret")
    monkeypatch.delenv("CREDITS_ENABLED", raising=False)
    import config

    importlib.reload(config)
    try:
        assert config.credits_enabled is False
        from users.quota import enforce_quota

        # Legacy path: paid generate is still the unconditional allow.
        result = enforce_quota(_ctx("paid"), "generate", repo, NOW)
        assert result.allowed
        assert "creditsRemaining" not in result.usage
    finally:
        # Clear env BEFORE reloading: monkeypatch's own teardown runs after
        # this fixture's, so reloading while AUTH_ENABLED is still set would
        # leave config.auth_enabled True for every subsequent test in the run.
        monkeypatch.delenv("AUTH_ENABLED", raising=False)
        monkeypatch.delenv("GUEST_TOKEN_SECRET", raising=False)
        importlib.reload(config)


# ---- Outpaint is charged at its own rate ----


def test_outpaint_charges_its_own_configured_cost(credits_on, repo, monkeypatch):
    """A price advertised on /pricing must be the price actually debited.

    /outpaint used to be enforced as "refine", so CREDITS_PER_OUTPAINT was
    advertised but never charged. With equal defaults nothing broke, which is
    exactly what made it a trap: changing one value alone would have made the
    UI show a price the backend did not take.
    """
    monkeypatch.setattr(credits_on, "credits_per_outpaint", 70)
    monkeypatch.setitem(credits_on.CREDIT_COSTS, "outpaint", 70)
    from users.quota import enforce_quota

    result = enforce_quota(_ctx("paid", "u_out"), "outpaint", repo, NOW)
    assert result.allowed
    assert result.usage["creditsCharged"] == 70
    assert result.usage["creditsRemaining"] == credits_on.paid_monthly_credits - 70


def test_outpaint_and_refine_are_independently_priced(credits_on, repo, monkeypatch):
    monkeypatch.setattr(credits_on, "credits_per_outpaint", 70)
    monkeypatch.setitem(credits_on.CREDIT_COSTS, "outpaint", 70)
    from users.quota import enforce_quota

    out = enforce_quota(_ctx("paid", "u_a"), "outpaint", repo, NOW)
    ref = enforce_quota(_ctx("paid", "u_b"), "refine", repo, NOW)
    assert out.usage["creditsCharged"] == 70
    assert ref.usage["creditsCharged"] == credits_on.credits_per_refine
    assert out.usage["creditsCharged"] != ref.usage["creditsCharged"]


def test_guests_are_blocked_from_outpaint_like_refine(credits_on, repo):
    from users.quota import enforce_quota

    result = enforce_quota(_ctx("guest", "guest#x"), "outpaint", repo, NOW)
    assert result.allowed is False
    assert result.reason == "guest_per_user"


def test_advertised_outpaint_cost_matches_enforced_cost(credits_on, repo):
    """The whole point of backend-served pricing, asserted end to end."""
    from api.pricing import get_pricing
    from users.quota import enforce_quota

    advertised = get_pricing()["creditCosts"]["outpaint"]
    charged = enforce_quota(_ctx("paid", "u_match"), "outpaint", repo, NOW).usage[
        "creditsCharged"
    ]
    assert advertised == charged


def test_advertised_generate_and_refine_costs_match_enforced(credits_on, repo):
    from api.pricing import get_pricing
    from users.quota import enforce_quota

    pricing = get_pricing()["creditCosts"]
    gen = enforce_quota(_ctx("paid", "u_g"), "generate", repo, NOW)
    ref = enforce_quota(_ctx("paid", "u_r"), "refine", repo, NOW)
    assert pricing["generate"] == gen.usage["creditsCharged"]
    assert pricing["refine"] == ref.usage["creditsCharged"]


# ---- Top-up semantics ----


def test_top_up_is_discarded_at_period_rollover(repo):
    """Documented behaviour, asserted so a silent change is caught.

    Renewal SETs a fresh allotment rather than adding to the balance, so a
    top-up lives only until the period lapses. That matches allotments not
    rolling over; the test exists so nobody changes it by accident.
    """
    repo.debit_credits("u_top", amount=100, allotment=500, period_end=NOW + 10, now=NOW)
    repo.grant_credits("u_top", 5000, now=NOW)
    assert repo.get_credit_balance("u_top")["creditsRemaining"] == 5400

    later = NOW + 11
    ok, item = repo.debit_credits(
        "u_top", amount=100, allotment=500, period_end=later + 86400, now=later
    )
    assert ok
    assert int(item["creditsRemaining"]) == 400, "top-up does not survive renewal"


def test_top_up_to_a_dormant_user_is_wiped_without_a_period(repo):
    """The trap: granting to a user with no open period achieves nothing."""
    repo.get_or_create_user("u_dormant", now=NOW)
    repo.grant_credits("u_dormant", 5000, now=NOW)
    assert repo.get_credit_balance("u_dormant")["creditsRemaining"] == 5000

    # Their next request takes the renewal path and overwrites the grant.
    ok, item = repo.debit_credits(
        "u_dormant", amount=100, allotment=500, period_end=NOW + 86400, now=NOW
    )
    assert ok
    assert int(item["creditsRemaining"]) == 400


def test_top_up_survives_when_it_opens_a_period(repo):
    """Passing period_end makes a dormant-account top-up actually stick."""
    repo.get_or_create_user("u_dormant2", now=NOW)
    repo.grant_credits("u_dormant2", 5000, now=NOW, period_end=NOW + 86400)

    ok, item = repo.debit_credits(
        "u_dormant2", amount=100, allotment=500, period_end=NOW + 86400, now=NOW
    )
    assert ok
    assert int(item["creditsRemaining"]) == 4900


def test_top_up_does_not_extend_an_active_period(repo):
    """A top-up must not silently postpone renewal."""
    repo.debit_credits("u_act", amount=100, allotment=500, period_end=NOW + 100, now=NOW)
    repo.grant_credits("u_act", 200, now=NOW, period_end=NOW + 999999)
    assert repo.get_credit_balance("u_act")["creditPeriodEnd"] == NOW + 100


# ---- Refund when a paid-for request produces nothing ----


def test_refund_helper_returns_the_exact_charge(credits_on, repo, monkeypatch):
    """A refund must equal the charge, or the ledger drifts."""
    import lambda_function
    from users.quota import enforce_quota

    monkeypatch.setattr(lambda_function, "_user_repo", repo)
    ctx = _ctx("paid", "u_refund")

    before = credits_on.paid_monthly_credits
    charged = enforce_quota(ctx, "generate", repo, NOW)
    assert repo.get_credit_balance("u_refund")["creditsRemaining"] == (
        before - credits_on.credits_per_generate
    )

    lambda_function._refund_credits(ctx, "generate", "corr-1")
    assert repo.get_credit_balance("u_refund")["creditsRemaining"] == before
    assert charged.usage["creditsCharged"] == credits_on.credits_per_generate


def test_refund_matches_the_charge_for_every_action(credits_on, repo, monkeypatch):
    import lambda_function
    from users.quota import enforce_quota

    monkeypatch.setattr(lambda_function, "_user_repo", repo)
    for kind, user in (("generate", "u_a"), ("refine", "u_b"), ("outpaint", "u_c")):
        ctx = _ctx("paid", user)
        enforce_quota(ctx, kind, repo, NOW)
        spent = credits_on.paid_monthly_credits - repo.get_credit_balance(user)[
            "creditsRemaining"
        ]
        lambda_function._refund_credits(ctx, kind, "corr-1")
        restored = repo.get_credit_balance(user)["creditsRemaining"]
        assert restored == credits_on.paid_monthly_credits, f"{kind} refund != charge"
        assert spent == credits_on.credit_cost(kind)


def test_no_refund_when_credits_disabled(repo, monkeypatch):
    """Nothing was charged, so nothing may be granted."""
    import config
    import lambda_function

    monkeypatch.setattr(lambda_function, "_user_repo", repo)
    monkeypatch.setattr(config, "credits_enabled", False)
    repo.get_or_create_user("u_off", now=NOW)
    lambda_function._refund_credits(_ctx("paid", "u_off"), "generate", "corr-1")
    assert repo.get_credit_balance("u_off")["creditsRemaining"] == 0


def test_no_refund_for_guests(credits_on, repo, monkeypatch):
    """Guests are not on the ledger, so a refund would mint credits."""
    import lambda_function

    monkeypatch.setattr(lambda_function, "_user_repo", repo)
    repo.get_or_create_user("guest#abc", now=NOW)
    lambda_function._refund_credits(_ctx("guest", "guest#abc"), "generate", "corr-1")
    assert repo.get_credit_balance("guest#abc")["creditsRemaining"] == 0


def test_refund_failure_is_swallowed(credits_on, repo, monkeypatch):
    """The caller is already on an error path; a failed refund must not raise."""
    import lambda_function

    monkeypatch.setattr(lambda_function, "_user_repo", repo)
    monkeypatch.setattr(
        repo,
        "grant_credits",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("dynamo down")),
    )
    # Must not propagate.
    lambda_function._refund_credits(_ctx("paid", "u_boom"), "generate", "corr-1")


def test_no_refund_when_tier_context_missing(credits_on, repo, monkeypatch):
    import lambda_function

    monkeypatch.setattr(lambda_function, "_user_repo", repo)
    lambda_function._refund_credits(None, "generate", "corr-1")
