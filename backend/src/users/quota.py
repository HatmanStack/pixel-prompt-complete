"""Tier-based quota enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import config
from users.repository import UserRepository
from users.tier import TierContext


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
    endpoint: Literal["generate", "refine"],
    repo: UserRepository,
    now: int,
) -> QuotaResult:
    if not config.auth_enabled:
        return QuotaResult(allowed=True, reason=None, reset_at=0, usage={})

    if ctx.tier == "guest":
        if endpoint == "refine":
            return QuotaResult(allowed=False, reason="guest_per_user", reset_at=0, usage={})
        # Global cap first.
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
        # Per-guest.
        assert ctx.guest_token_id is not None
        ok, item = repo.increment_guest_generate(
            ctx.guest_token_id,
            config.guest_generate_limit,
            config.guest_window_seconds,
            now,
        )
        usage, reset = _usage(
            item,
            "generateCount",
            config.guest_generate_limit,
            "windowStart",
            config.guest_window_seconds,
        )
        return QuotaResult(
            allowed=ok,
            reason=None if ok else "guest_per_user",
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
        return QuotaResult(allowed=True, reason=None, reset_at=0, usage={})
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
