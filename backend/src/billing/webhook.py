"""POST /stripe/webhook handler.

Verifies Stripe signatures against the raw request body and dispatches
events to idempotent handlers that update the users table.
"""

from __future__ import annotations

import base64
import json
import traceback
from typing import Any

import stripe

import config
from billing.stripe_client import get_stripe
from notifications import sender as email_sender
from notifications import templates as email_templates
from users.repository import UserRepository
from utils.logger import StructuredLogger


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": config.cors_allowed_origin,
        },
        "body": json.dumps(body),
    }


def _get_sig_header(event: dict[str, Any]) -> str:
    headers = event.get("headers") or {}
    for k, v in headers.items():
        if k.lower() == "stripe-signature":
            return v or ""
    return ""


def _raw_body(event: dict[str, Any]) -> str:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        return base64.b64decode(body).decode("utf-8")
    return body


def _send_lifecycle_email(repo: UserRepository, user_id: str, template_fn, *template_args) -> None:
    """Send a lifecycle email if the user has an email address.

    Fire-and-forget: errors are logged but never raised.
    """
    try:
        user = repo.get_user(user_id)
        if not user:
            return
        email = user.get("email")
        if not email:
            return
        subject, html, text = template_fn(email, *template_args)
        email_sender.send_email(email, subject, html, text)
    except Exception as e:
        StructuredLogger.warning(f"Lifecycle email failed for {user_id}: {e}")


def _user_id_from_object(obj: dict[str, Any]) -> str | None:
    """Extract the userId (Cognito sub) from a Stripe object.

    Checkout sessions carry ``client_reference_id``; subscriptions and
    invoices carry ``metadata.userId`` set at checkout time (see
    ``billing.checkout.handle_billing_checkout``).
    """
    ref = obj.get("client_reference_id")
    if ref:
        return ref
    metadata = obj.get("metadata") or {}
    return metadata.get("userId")


def _on_checkout_completed(obj: dict[str, Any], repo: UserRepository) -> None:
    user_id = _user_id_from_object(obj)
    if not user_id:
        return
    fields: dict[str, Any] = {}
    if obj.get("customer"):
        fields["stripeCustomerId"] = obj["customer"]
    if obj.get("subscription"):
        fields["stripeSubscriptionId"] = obj["subscription"]
    fields["subscriptionStatus"] = "active"
    repo.set_tier(user_id, "paid", **fields)
    repo.increment_revenue_counter("activeSubscribers", 1)
    _send_lifecycle_email(repo, user_id, email_templates.welcome_email)


def _on_subscription_upsert(obj: dict[str, Any], repo: UserRepository) -> None:
    user_id = _user_id_from_object(obj)
    if not user_id:
        return
    status = obj.get("status", "active")
    tier = "paid" if status in ("active", "trialing") else "free"
    fields: dict[str, Any] = {
        "subscriptionStatus": status,
        "stripeSubscriptionId": obj.get("id", ""),
    }
    if obj.get("customer"):
        fields["stripeCustomerId"] = obj["customer"]
    repo.set_tier(user_id, tier, **fields)


def _on_subscription_deleted(obj: dict[str, Any], repo: UserRepository) -> None:
    user_id = _user_id_from_object(obj)
    if not user_id:
        return
    repo.set_tier(
        user_id,
        "free",
        subscriptionStatus="canceled",
        stripeSubscriptionId="",
    )
    repo.decrement_revenue_counter("activeSubscribers", 1)
    repo.increment_revenue_counter("monthlyChurn", 1)
    _send_lifecycle_email(repo, user_id, email_templates.subscription_cancelled_email)


def _on_payment_failed(obj: dict[str, Any], repo: UserRepository) -> None:
    user_id = _user_id_from_object(obj)
    if not user_id:
        return
    user = repo.get_user(user_id)
    if user is None:
        return
    current_tier = user.get("tier", "free")
    # Keep tier as-is; only mark status as past_due.
    repo.set_tier(user_id, current_tier, subscriptionStatus="past_due")
    _send_lifecycle_email(repo, user_id, email_templates.payment_failed_email)


_DISPATCH = {
    "checkout.session.completed": _on_checkout_completed,
    "customer.subscription.created": _on_subscription_upsert,
    "customer.subscription.updated": _on_subscription_upsert,
    "customer.subscription.deleted": _on_subscription_deleted,
    "invoice.payment_failed": _on_payment_failed,
}


def handle_stripe_webhook(
    event: dict[str, Any],
    repo: UserRepository,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Verify Stripe signature and dispatch to event handlers."""
    if not config.billing_enabled:
        return _response(501, {"error": "billing disabled"})

    raw_body = _raw_body(event)
    sig_header = _get_sig_header(event)
    if not sig_header:
        return _response(400, {"error": "invalid signature"})

    # Ensure stripe api key is initialized (side effect of get_stripe).
    try:
        get_stripe()
    except RuntimeError:
        return _response(500, {"error": "stripe not configured"})

    try:
        stripe_event = stripe.Webhook.construct_event(
            raw_body, sig_header, config.stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        return _response(400, {"error": "invalid signature"})
    except ValueError:
        return _response(400, {"error": "invalid payload"})

    event_type = stripe_event["type"]
    handler = _DISPATCH.get(event_type)
    if handler:
        try:
            raw_obj = stripe_event["data"]["object"]
            # Normalize StripeObject to a plain dict so handlers can use
            # ``.get()`` without tripping StripeObject's custom __getattr__.
            if hasattr(raw_obj, "to_dict_recursive"):
                obj = raw_obj.to_dict_recursive()
            elif hasattr(raw_obj, "to_dict"):
                obj = raw_obj.to_dict()
            else:
                obj = raw_obj
            handler(obj, repo)
        except Exception as e:
            StructuredLogger.error(
                f"Webhook handler error for {event_type}: {e}",
                correlation_id=correlation_id,
                traceback=traceback.format_exc(),
            )
            return _response(500, {"error": "handler failed"})
    return _response(200, {"received": True})
