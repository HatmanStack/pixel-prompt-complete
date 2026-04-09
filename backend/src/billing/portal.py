"""POST /billing/portal handler: create a Stripe Customer Portal session."""

from __future__ import annotations

import json
import traceback
from typing import Any

import stripe

import config
from billing.stripe_client import get_stripe
from users.repository import UserRepository
from users.tier import extract_claims
from utils import error_responses
from utils.logger import StructuredLogger


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": config.cors_allowed_origin,
            "Access-Control-Allow-Credentials": "true",
        },
        "body": json.dumps(body),
    }


def handle_billing_portal(
    event: dict[str, Any],
    repo: UserRepository,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Return a Stripe Customer Portal session URL for the authenticated user."""
    if not config.billing_enabled:
        return _response(501, {"error": "billing disabled"})

    claims = extract_claims(event)
    if not claims:
        return _response(401, error_responses.auth_required())

    user_id = claims["sub"]
    try:
        user = repo.get_user(user_id) or {}
        customer_id = user.get("stripeCustomerId")
        if not customer_id:
            return _response(
                409,
                {"error": "no_subscription", "message": "No Stripe customer for user"},
            )

        stripe_mod = get_stripe()
        session = stripe_mod.billing_portal.Session.create(
            customer=customer_id,
            return_url=config.stripe_portal_return_url,
        )
        return _response(200, {"url": session["url"]})
    except stripe.error.StripeError as e:
        StructuredLogger.error(
            f"Stripe portal failed: {e}",
            correlation_id=correlation_id,
        )
        return _response(502, {"error": "stripe_error", "message": str(e)})
    except Exception as e:
        StructuredLogger.error(
            f"Portal error: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return _response(500, error_responses.internal_server_error())
