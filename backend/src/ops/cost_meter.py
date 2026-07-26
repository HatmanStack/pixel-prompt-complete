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

# Daily accumulators are retained long enough to answer "what did last quarter
# cost?" then expire. Without this the table grows by one item per day forever,
# which is a poor look for a cost-control feature.
SPEND_ITEM_TTL_SECONDS = 400 * 86400


def _day_key(now: int) -> str:
    """UTC date bucket. UTC, not local, so the ceiling resets predictably."""
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")


def spend_item_key(now: int) -> str:
    return f"spend#{_day_key(now)}"


def _month_key(now: int) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m")


def monthly_spend_item_key(now: int) -> str:
    """Accumulator for the calendar month.

    A daily ceiling alone does not bound a month: even the current $25/day
    permits roughly $750 across 30 days. This is the item the monthly
    ceiling reads.
    """
    return f"spend#{_month_key(now)}"


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

        # Daily items are authoritative. The monthly item is a fast-path cache
        # so a ceiling check on the request path costs one read instead of
        # summing 31 days.
        #
        # These are two writes, so one can fail while the other lands. That is
        # tolerated rather than made transactional: the daily snapshot job
        # recomputes the monthly total from the daily items, so any divergence
        # is repaired within a day and the authoritative record is the one
        # written first.
        try:
            self._repo.add_counters(
                spend_item_key(now),
                deltas,
                now=now,
                ttl=now + SPEND_ITEM_TTL_SECONDS,
            )
        except Exception as e:
            StructuredLogger.error(
                f"Cost meter failed to record daily spend: {e}",
                totalMicros=total,
                tier=tier,
            )

        try:
            self._repo.add_counters(
                monthly_spend_item_key(now),
                deltas,
                now=now,
                ttl=now + SPEND_ITEM_TTL_SECONDS,
            )
        except Exception as e:
            StructuredLogger.error(
                f"Cost meter failed to record monthly spend: {e}",
                totalMicros=total,
            )

        # Mirror to CloudWatch so spend can be alarmed on. DynamoDB holds the
        # authoritative number; this is what can actually page someone.
        try:
            from ops.metrics import emit_spend_metric

            emit_spend_metric(total, tier)
        except Exception as e:
            StructuredLogger.error(f"Failed to mirror spend to CloudWatch: {e}")

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
        return self._read_spend(spend_item_key(now))

    def get_monthly_spend(self, now: int | None = None) -> dict[str, Any]:
        """Read this calendar month's accumulator."""
        if now is None:
            now = int(time.time())
        return self._read_spend(monthly_spend_item_key(now))

    def _read_spend(self, key: str) -> dict[str, Any]:
        item = self._repo.get_user(key)
        if not item:
            return {"totalMicros": 0}
        return {
            k: int(v)
            for k, v in item.items()
            if k not in ("userId", "updatedAt", "ttl")
        }


def reconcile_monthly_spend(repo: Any, now: int) -> dict[str, int]:
    """Recompute the month's accumulator from the authoritative daily items.

    The monthly item is a cache written alongside each daily write, so a
    partial failure can leave it under-counting, and an under-counting
    monthly total means the ceiling that caps the invoice trips later than
    it should.

    Rather than make the two writes transactional, this recomputes the month
    from its days and corrects the difference. Called from the daily snapshot,
    so divergence is bounded by one day.

    Returns {"expected", "recorded", "corrected"} in micro-dollars.
    """
    meter = CostMeter(repo)
    month = _month_key(now)
    expected = 0
    day = now
    # Walk back to the start of the month.
    for _ in range(31):
        if _month_key(day) != month:
            break
        expected += int(meter.get_daily_spend(now=day).get("totalMicros", 0))
        day -= 86400

    recorded = int(meter.get_monthly_spend(now=now).get("totalMicros", 0))
    drift = expected - recorded
    if drift:
        StructuredLogger.warning(
            "Monthly spend accumulator drifted from the daily totals; correcting",
            month=month,
            expectedMicros=expected,
            recordedMicros=recorded,
            driftMicros=drift,
        )
        repo.add_counters(
            monthly_spend_item_key(now),
            {"totalMicros": drift},
            now=now,
            ttl=now + SPEND_ITEM_TTL_SECONDS,
        )
    return {"expected": expected, "recorded": recorded, "corrected": drift}
