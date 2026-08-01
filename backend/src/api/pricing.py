"""GET /pricing - the single source of truth for what things cost.

Serving prices from the backend rather than ``VITE_`` build-time variables
means a price experiment is a config change, not a frontend rebuild and
redeploy. That friction is the difference between actually finding the price
edges and never running the experiment.

It also removes a class of bug: the UI cannot advertise a price the backend
does not enforce, because both read the same values.

Public and unauthenticated by design — prices are not a secret, and the
upgrade modal must render them before a user has an account.
"""

from __future__ import annotations

import time
from typing import Any

import config
from utils.http import json_response
from utils.logger import StructuredLogger

# Stripe is the authority on what a customer is actually charged. Cached at
# module level: /pricing is public and hit on every page load, and a price
# changes far less often than it is read.
# (unit_amount_cents_or_None, fetched_at). None is cached too — see below.
_price_cache: tuple[int | None, int] | None = None
_PRICE_CACHE_TTL_SECONDS = 900


def reset_price_cache() -> None:
    """Drop the cached Stripe amount (tests, and after a price change)."""
    global _price_cache
    _price_cache = None


def _stripe_price_usd_cents() -> int | None:
    """The amount Stripe will actually charge, or None if unavailable.

    ``PAID_PRICE_USD_CENTS`` and ``STRIPE_PRICE_ID`` are separate settings, so
    a stack update can advertise one amount and charge another. Reading the
    real amount from Stripe removes that whole class of mismatch; the config
    value stays as the fallback for when billing is off or Stripe is
    unreachable, so a public endpoint never depends on a third party being up.
    """
    global _price_cache
    if not config.billing_enabled or not config.stripe_price_id:
        return None

    now = int(time.time())
    if _price_cache and now - _price_cache[1] < _PRICE_CACHE_TTL_SECONDS:
        return _price_cache[0]

    try:
        from billing.stripe_client import get_stripe

        stripe_mod = get_stripe()
        price = stripe_mod.Price.retrieve(config.stripe_price_id)
        amount = price.get("unit_amount") if hasattr(price, "get") else None
        # `is None`, not falsiness. A fully discounted price has a
        # unit_amount of 0, which is a real answer -- treating it as "no
        # answer" would advertise the configured non-zero price instead.
        if amount is None:
            # Same reasoning as the except branch below: a price we cannot
            # read is not a price change. Stripe returns a null unit_amount
            # for tiered and graduated pricing, so caching None here would
            # quietly swap every visitor onto PAID_PRICE_USD_CENTS the moment
            # someone migrated the plan -- the config-vs-Stripe mismatch this
            # module exists to eliminate, arrived at through this module.
            last_known = _price_cache[0] if _price_cache else None
            StructuredLogger.warning(
                "Stripe price carried no unit_amount (tiered or graduated?); "
                f"serving {'last known' if last_known is not None else 'configured'} value",
                stripePriceId=config.stripe_price_id,
                lastKnownCents=last_known,
            )
            _price_cache = (last_known, now)
            return last_known
        _price_cache = (int(amount), now)
        return int(amount)
    except Exception as e:
        # Serve the last amount Stripe actually confirmed, if there is one.
        # Falling back to the configured value once the real price is known
        # would quietly change what every visitor is quoted for the length of
        # the TTL — and the two are allowed to disagree, which is the whole
        # reason this function exists. An outage is not a price change.
        last_known = _price_cache[0] if _price_cache else None
        # `is not None`, matching the branch above: a confirmed price of 0 is
        # a real price and is what gets served here, so reporting it as the
        # "configured" value would tell an operator reading this during an
        # outage the opposite of what happened.
        StructuredLogger.warning(
            "Could not read price from Stripe, serving "
            f"{'last known' if last_known is not None else 'configured'} value: {e}",
            stripePriceId=config.stripe_price_id,
            lastKnownCents=last_known,
        )
        # Cache the outcome for the same TTL. /pricing is public and hit on
        # every page load, so without this a Stripe outage means every single
        # visitor blocks on a failing upstream call.
        _price_cache = (last_known, now)
        return last_known


def _tiers() -> list[dict[str, Any]]:
    """Tiers the backend can actually enforce.

    Deliberately only free and paid: those are the tiers ``resolve_tier``
    produces and ``quota`` enforces. Advertising a plan the tier system cannot
    grant would sell something that does not exist.
    """
    stripe_amount = _stripe_price_usd_cents()
    paid_price = stripe_amount if stripe_amount is not None else config.paid_price_usd_cents
    if stripe_amount is not None and stripe_amount != config.paid_price_usd_cents:
        # Stripe wins — it is what the customer is charged — but a mismatch
        # means the deployed config is lying and should be corrected.
        StructuredLogger.error(
            "PAID_PRICE_USD_CENTS disagrees with the Stripe price; serving the Stripe amount",
            configuredCents=config.paid_price_usd_cents,
            stripeCents=stripe_amount,
        )

    return [
        {
            "id": "free",
            "name": "Free",
            "priceUsdCents": 0,
            "monthlyCredits": config.free_monthly_credits,
            "allModels": True,
            "renewal": "fixed_window",
        },
        {
            "id": "paid",
            "name": "Pro",
            "priceUsdCents": paid_price,
            "monthlyCredits": config.paid_monthly_credits,
            "allModels": True,
            # Paid allotments renew on Stripe's own billing boundary, which
            # runs 28-31 days, not on a fixed clock.
            "renewal": "stripe_billing_period",
        },
    ]


def get_pricing() -> dict[str, Any]:
    """Build the pricing payload."""
    return {
        "currency": "usd",
        "creditsEnabled": config.credits_enabled,
        "billingEnabled": config.billing_enabled,
        # Centi-credits: 100 = one credit. Exposed raw so the client can
        # render fractions without the server guessing a display format.
        "centiCreditsPerCredit": 100,
        "creditCosts": {
            "generate": config.credits_per_generate,
            "refine": config.credits_per_refine,
            "outpaint": config.credits_per_outpaint,
        },
        "overageUsdCentsPerCredit": config.overage_usd_cents_per_credit,
        "tiers": _tiers(),
    }


def handle_pricing(event: dict[str, Any], correlation_id: str | None = None) -> dict[str, Any]:
    """GET /pricing - public pricing and credit costs."""
    return json_response(
        200,
        get_pricing(),
        # Prices change rarely and every client needs them on load.
        extra_headers={"Cache-Control": "public, max-age=300"},
    )
