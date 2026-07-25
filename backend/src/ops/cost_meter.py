"""Dollar-denominated spend metering.

The system counted API calls but never dollars, which made it impossible to
price: a "generate" and a "refine" differ by ~4x in cost, and per-model costs
differ by ~2x between the cheapest and most expensive provider. Counting calls
hides both.

Everything here is in **micro-dollars** (1e-6 USD) as integers. DynamoDB's
``ADD`` on a float would accumulate drift across millions of increments, and
money that drifts is worse than money that is merely approximate.

Storage layout, all in the existing users table:

* ``spend#<YYYY-MM-DD>`` — live daily accumulator. Attributes: ``totalMicros``,
  ``<label>Micros`` per model plus ``enhance``, and ``<tier>TierMicros``
  buckets. This is what the daily spend ceiling (and its alarms) reads.
* the user's own record — ``periodSpendMicros``, for per-user reporting and
  overage billing.

Metering is fire-and-forget: a failure here is logged loudly but never
propagates. Failing a paid user's image generation because a metrics write
timed out would be a worse outcome than a gap in the spend chart. The tradeoff
is that sustained write failures under-count spend, so the errors are logged at
ERROR precisely so they can be alarmed on.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import config
from users.repository import UserRepository
from utils.logger import StructuredLogger


def _day_key(now: int) -> str:
    """UTC date bucket. UTC, not local, so the ceiling resets predictably."""
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")


def spend_item_key(now: int) -> str:
    return f"spend#{_day_key(now)}"


class CostMeter:
    """Records what each request actually cost, in dollars."""

    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    def record(
        self,
        *,
        costs: dict[str, int],
        tier: str,
        user_id: str | None = None,
        now: int | None = None,
    ) -> int:
        """Record a request's spend. Returns the total in micro-dollars.

        ``costs`` maps a label (model name, or ``"enhance"``) to micro-dollars.
        Labels are aggregated into one atomic write per item so a request that
        hit four models costs two UpdateItems, not five.
        """
        if now is None:
            now = int(time.time())
        costs = {k: v for k, v in costs.items() if v}
        total = sum(costs.values())
        if total <= 0:
            return 0

        deltas: dict[str, int] = {"totalMicros": total}
        for label, micros in costs.items():
            deltas[f"{label}Micros"] = micros
        # Tier bucket: shows whether spend is coming from paying users or from
        # the free tier, which is the largest single exposure at 4-model access.
        deltas[f"{tier}TierMicros"] = total

        try:
            self._repo.add_counters(spend_item_key(now), deltas, now=now)
        except Exception as e:
            StructuredLogger.error(
                f"Cost meter failed to record daily spend: {e}",
                totalMicros=total,
                tier=tier,
            )

        # Per-user spend. Guests are tracked under their own guest# record;
        # anonymous requests (auth disabled) have no record to attribute to.
        if user_id and user_id != "anon":
            try:
                self._repo.add_counters(user_id, {"periodSpendMicros": total}, now=now)
            except Exception as e:
                StructuredLogger.error(
                    f"Cost meter failed to record user spend for {user_id}: {e}",
                    totalMicros=total,
                )
        return total

    def record_models(
        self,
        *,
        model_names: list[str],
        operation: str,
        tier: str,
        user_id: str | None = None,
        include_enhance: bool = False,
        now: int | None = None,
    ) -> int:
        """Convenience wrapper: price a set of models for one operation."""
        costs = {name: config.model_cost_micros(name, operation) for name in model_names}
        if include_enhance:
            costs["enhance"] = config.enhance_cost_usd_micros
        return self.record(costs=costs, tier=tier, user_id=user_id, now=now)

    def get_daily_spend(self, now: int | None = None) -> dict[str, Any]:
        """Read today's accumulator. Missing item means nothing spent yet."""
        if now is None:
            now = int(time.time())
        item = self._repo.get_user(spend_item_key(now))
        if not item:
            return {"totalMicros": 0}
        return {k: int(v) for k, v in item.items() if k not in ("userId", "updatedAt")}
