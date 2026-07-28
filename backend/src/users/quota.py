"""Tier-based quota enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import config
from ops import store_breaker
from users.repository import UserRepository
from users.tier import TierContext
from utils.logger import StructuredLogger


@dataclass(frozen=True)
class QuotaResult:
    allowed: bool
    reason: str | None
    reset_at: int
    usage: dict = field(default_factory=dict)


def _usage(
    item: dict, counter: str, limit: int, window_field: str, window: int
) -> tuple[dict, int]:
    used = int(item.get(counter, 0) or 0)
    start = int(item.get(window_field, 0) or 0)
    return {"used": used, "limit": limit}, start + window


def enforce_quota(
    ctx: TierContext,
    endpoint: Literal["generate", "refine", "outpaint"],
    repo: UserRepository,
    now: int,
) -> QuotaResult:
    # NOTE: deliberately not gated on config.auth_enabled. Auth answers "who
    # is this"; quota answers "how much may they have". Conflating them is why
    # an open deployment was also an unlimited one.
    if ctx.tier == "anon":
        return _enforce_anon(ctx, endpoint, repo, now)

    # Suspension check: non-guest users with isSuspended=true are blocked.
    if ctx.tier != "guest" and repo.is_suspended(ctx.user_id):
        return QuotaResult(allowed=False, reason="suspended", reset_at=0)

    # Credit ledger. Replaces call-counting for free and paid users; guests
    # stay on the legacy rate limit because a guest identity is currently
    # honour-system (drop the cookie, get a new one), so a guest credit
    # balance would bound nothing until P0-D binds it to something real.
    if config.credits_enabled and ctx.tier in ("free", "paid"):
        return _enforce_credits(ctx, endpoint, repo, now)

    if ctx.tier == "guest":
        # Guest refine/outpaint is refused with a 402 in lambda_function before
        # enforce_quota is reached, so only "generate" arrives here. Do not
        # re-add a refine branch: it would be unreachable.
        #
        # Identity BEFORE metering. Ordered first because the per-IP bucket is
        # the one a caller cannot reset -- dropping the cookie mints a fresh
        # token, but the IP hash persists -- so consuming from it and then
        # refusing the request spends an allowance the caller has no way to
        # recover, for a request that was never going to be served.
        if ctx.guest_token_id is None:
            # Was a bare `assert`. Under `python -O` the check vanishes and an
            # unidentifiable guest is metered against nothing, which is how a
            # guest bucket becomes unlimited; without -O it surfaced as an
            # AssertionError with no diagnostic, inside a fail-open wrapper, in
            # a function whose every other failure returns a QuotaResult.
            #
            # Denying rather than failing open, unlike the store-error paths:
            # an unreachable store is a transient fact about infrastructure,
            # whereas reaching here means resolve_tier produced a guest context
            # with no token id, which is a bug in this process.
            StructuredLogger.error(
                "Guest context has no token id; denying rather than metering "
                "an unidentifiable caller against nothing"
            )
            return QuotaResult(allowed=False, reason="guest_identity_missing", reset_at=0)

        # Per-IP next: it is the only guest bucket a caller cannot reset.
        # Dropping the cookie mints a new token with a fresh per-token
        # counter, so checking that alone bounds nothing.
        if ctx.ip_hash:
            ip_ok, ip_item = repo.increment_guest_ip(
                ctx.ip_hash,
                config.guest_ip_generate_limit,
                config.guest_ip_window_seconds,
                now,
            )
            if not ip_ok:
                usage, reset = _usage(
                    ip_item,
                    "generateCount",
                    config.guest_ip_generate_limit,
                    "windowStart",
                    config.guest_ip_window_seconds,
                )
                return QuotaResult(allowed=False, reason="guest_ip", reset_at=reset, usage=usage)

        # Per-guest next so denied guests don't consume the global pool.
        ok, item = repo.increment_guest_generate(
            ctx.guest_token_id,
            config.guest_generate_limit,
            config.guest_window_seconds,
            now,
        )
        if not ok:
            usage, reset = _usage(
                item,
                "generateCount",
                config.guest_generate_limit,
                "windowStart",
                config.guest_window_seconds,
            )
            return QuotaResult(
                allowed=False,
                reason="guest_per_user",
                reset_at=reset,
                usage=usage,
            )
        # Global cap (only reached if per-guest succeeded).
        ok_global, gitem = repo.increment_global_guest(
            config.guest_global_limit, config.guest_global_window_seconds, now
        )
        if not ok_global:
            usage, reset = _usage(
                gitem,
                "generateCount",
                config.guest_global_limit,
                "windowStart",
                config.guest_global_window_seconds,
            )
            return QuotaResult(
                allowed=False,
                reason="guest_global",
                reset_at=reset,
                usage=usage,
            )
        usage, reset = _usage(
            item,
            "generateCount",
            config.guest_generate_limit,
            "windowStart",
            config.guest_window_seconds,
        )
        return QuotaResult(
            allowed=True,
            reason=None,
            reset_at=reset,
            usage=usage,
        )

    if ctx.tier == "free":
        if endpoint == "generate":
            ok, item = repo.increment_generate(
                ctx.user_id,
                config.free_window_seconds,
                config.free_generate_limit,
                now,
            )
            usage, reset = _usage(
                item,
                "generateCount",
                config.free_generate_limit,
                "windowStart",
                config.free_window_seconds,
            )
            return QuotaResult(
                allowed=ok,
                reason=None if ok else "free_generate",
                reset_at=reset,
                usage=usage,
            )
        ok, item = repo.increment_refine(
            ctx.user_id,
            config.free_window_seconds,
            config.free_refine_limit,
            now,
        )
        usage, reset = _usage(
            item,
            "refineCount",
            config.free_refine_limit,
            "windowStart",
            config.free_window_seconds,
        )
        return QuotaResult(
            allowed=ok,
            reason=None if ok else "free_refine",
            reset_at=reset,
            usage=usage,
        )

    # paid
    if endpoint == "generate":
        # Was unconditionally allowed. Generation runs four providers and is
        # the most expensive thing the product does; leaving it bounded only
        # by ceilings shared across all users meant one account could consume
        # the organisation's entire day. Its own counter, not dailyCount: a
        # generation and a refinement are priced apart everywhere else.
        ok, item = repo.increment_daily_generate(
            ctx.user_id,
            config.paid_window_seconds,
            config.paid_daily_generate_limit,
            now,
        )
        usage, reset = _usage(
            item,
            "dailyGenerateCount",
            config.paid_daily_generate_limit,
            "dailyResetAt",
            config.paid_window_seconds,
        )
        return QuotaResult(
            allowed=ok,
            reason=None if ok else "paid_daily_generate",
            reset_at=reset,
            usage=usage,
        )
    ok, item = repo.increment_daily(
        ctx.user_id,
        config.paid_window_seconds,
        config.paid_daily_limit,
        now,
    )
    usage, reset = _usage(
        item,
        "dailyCount",
        config.paid_daily_limit,
        "dailyResetAt",
        config.paid_window_seconds,
    )
    return QuotaResult(
        allowed=ok,
        reason=None if ok else "paid_daily",
        reset_at=reset,
        usage=usage,
    )


def _credit_period_end(ctx: TierContext, repo: UserRepository, now: int) -> int:
    """When the current allotment period ends, for ``ctx``'s tier.

    Paid periods follow Stripe's own subscription boundary rather than a fixed
    clock: Stripe's monthly cycles run 28-31 days, so a fixed 30-day window
    would grant credits before the customer is billed in some months and leave
    them short after renewal in others.
    """
    if ctx.tier == "paid":
        item = repo.get_user(ctx.user_id) or {}
        stripe_end = int(item.get("stripeCurrentPeriodEnd", 0) or 0)
        if stripe_end > now:
            return stripe_end
        # No usable Stripe boundary (webhook missed, or a subscription that
        # predates period persistence). Fall back rather than leave a paying
        # customer at zero — under-charging beats wrongly denying service.
        return now + config.paid_credit_fallback_period_seconds
    return now + config.free_credit_period_seconds


def _enforce_credits(
    ctx: TierContext,
    endpoint: str,
    repo: UserRepository,
    now: int,
) -> QuotaResult:
    """Debit the request's credit cost, or deny if the balance is short."""
    cost = config.credit_cost(endpoint)
    allotment = config.monthly_credit_allotment(ctx.tier)
    period_end = _credit_period_end(ctx, repo, now)

    ok, item = repo.debit_credits(
        ctx.user_id,
        amount=cost,
        allotment=allotment,
        period_end=period_end,
        now=now,
    )
    remaining = int(item.get("creditsRemaining", 0) or 0)
    reset_at = int(item.get("creditPeriodEnd", period_end) or period_end)
    usage = {
        "creditsRemaining": remaining,
        "creditsAllotment": allotment,
        "creditsCharged": cost if ok else 0,
    }
    return QuotaResult(
        allowed=ok,
        reason=None if ok else "insufficient_credits",
        reset_at=reset_at,
        usage=usage,
    )


def _enforce_anon(
    ctx: TierContext,
    endpoint: str,
    repo: UserRepository,
    now: int,
) -> QuotaResult:
    """Meter an unauthenticated caller against their source IP.

    With auth off there is no account to bind to, so the IP is the only
    identifier available. Same caveat as the guest IP bucket: an IP is not a
    person, so these limits are abuse ceilings rather than fair-use quotas.
    """
    if not ctx.ip_hash:
        # No source IP to meter against. Allowing is the lesser evil: the
        # global spend ceiling still bounds the blast radius, whereas denying
        # would break every caller behind a proxy that strips the address.
        return QuotaResult(allowed=True, reason=None, reset_at=0, usage={})

    is_generate = endpoint == "generate"
    limit = config.anon_generate_limit if is_generate else config.anon_refine_limit
    counter = "generateCount" if is_generate else "refineCount"
    key = f"anon#{ctx.ip_hash}"

    try:
        ok, item = repo.increment_anon(key, counter, limit, config.anon_window_seconds, now)
    except Exception as e:
        # Counted by the store breaker: this is one of the seven sites that
        # swallow a store error, and they all read the same table.
        store_breaker.record_store_result(False)
        # Fail OPEN on a store error, matching the spend ceiling. An
        # unreachable counter is not evidence the caller is over limit, and
        # 500ing every request because the quota store hiccuped is a
        # self-inflicted outage. The global spend ceiling still bounds the
        # blast radius, and this logs at ERROR so a persistent failure — which
        # would mean silently unmetered traffic — is alarmable rather than
        # invisible.
        StructuredLogger.error(f"Anon quota check failed, allowing request: {e}")
        return QuotaResult(allowed=True, reason=None, reset_at=0, usage={})
    store_breaker.record_store_result(True)
    usage, reset = _usage(item, counter, limit, "windowStart", config.anon_window_seconds)
    return QuotaResult(
        allowed=ok,
        reason=None if ok else f"anon_{endpoint}",
        reset_at=reset,
        usage=usage,
    )
