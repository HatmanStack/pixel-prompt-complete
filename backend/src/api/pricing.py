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

import json
from typing import Any

import config


def _tiers() -> list[dict[str, Any]]:
    """Tiers the backend can actually enforce.

    Deliberately only free and paid: those are the tiers ``resolve_tier``
    produces and ``quota`` enforces. Advertising a plan the tier system cannot
    grant would sell something that does not exist.
    """
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
            "priceUsdCents": config.paid_price_usd_cents,
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


def handle_pricing(
    event: dict[str, Any], correlation_id: str | None = None
) -> dict[str, Any]:
    """GET /pricing - public pricing and credit costs."""
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": config.cors_allowed_origin,
            # Prices change rarely and every client needs them on load.
            "Cache-Control": "public, max-age=300",
        },
        "body": json.dumps(get_pricing()),
    }
