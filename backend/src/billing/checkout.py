"""POST /billing/checkout handler: create a Stripe Checkout Session."""

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


def handle_billing_checkout(
    event: dict[str, Any],
    repo: UserRepository,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Create a Stripe Checkout Session for the configured subscription price."""
    if not config.billing_enabled:
        return _response(501, {"error": "billing disabled"})

    claims = extract_claims(event)
    if not claims:
        return _response(401, error_responses.auth_required())

    user_id = claims["sub"]
    email = claims.get("email")

    try:
        stripe_mod = get_stripe()
        user = repo.get_or_create_user(user_id, email=email)
        customer_id = user.get("stripeCustomerId")
        if not customer_id:
            customer = stripe_mod.Customer.create(
                email=email,
                metadata={"userId": user_id},
            )
            customer_id = customer["id"]
            repo.set_stripe_customer_id(user_id, customer_id)

        session = stripe_mod.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": config.stripe_price_id, "quantity": 1}],
            success_url=config.stripe_success_url,
            cancel_url=config.stripe_cancel_url,
            client_reference_id=user_id,
        )
        return _response(200, {"url": session["url"]})
    except stripe.error.StripeError as e:
        StructuredLogger.error(
            f"Stripe checkout failed: {e}",
            correlation_id=correlation_id,
        )
        return _response(502, {"error": "stripe_error", "message": str(e)})
    except Exception as e:
        StructuredLogger.error(
            f"Checkout error: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return _response(500, error_responses.internal_server_error())
