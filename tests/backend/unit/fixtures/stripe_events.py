"""Helpers to build signed Stripe webhook payloads for tests.

The object builders below mirror the shape Stripe actually sends. In
particular:

* ``client_reference_id`` exists **only** on Checkout Sessions. It is not a
  field on Subscription or Invoice objects.
* ``metadata`` on a Subscription is ``{}`` unless ``subscription_data.metadata``
  was passed at checkout, so any test that hand-injects ``metadata.userId``
  into a subscription is testing a payload Stripe never emits.

Tests that need a user resolved from a subscription event should seed the
user's ``stripeCustomerId`` and let the webhook's reverse lookup find them —
that is the path real traffic takes.
"""

from __future__ import annotations

import hmac
import itertools
import json
import time
from hashlib import sha256
from typing import Any

# Stripe event ids are unique per delivery. Default to a fresh one per call so
# tests cannot accidentally collide in the webhook dedup table; tests that
# exercise redelivery pass an explicit id.
_event_counter = itertools.count(1)


def sign_payload(payload: str, secret: str, timestamp: int | None = None) -> str:
    """Return a Stripe-Signature header for ``payload``.

    Mirrors ``stripe.WebhookSignature``'s v1 scheme: ``t=<ts>,v1=<hmac>``.
    """
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.{payload}".encode()
    sig = hmac.new(secret.encode(), signed_payload, sha256).hexdigest()
    return f"t={ts},v1={sig}"


def build_event(
    event_type: str, obj: dict[str, Any], event_id: str | None = None
) -> str:
    """Return a JSON-encoded Stripe event payload.

    ``event_id`` defaults to a unique value, matching Stripe's behaviour.
    """
    if event_id is None:
        event_id = f"evt_test_{next(_event_counter)}"
    return json.dumps(
        {
            "id": event_id,
            "object": "event",
            "api_version": "2024-06-20",
            "created": 1679609767,
            "livemode": False,
            "type": event_type,
            "data": {"object": obj},
        }
    )


def checkout_session(
    *,
    user_id: str,
    customer: str,
    subscription: str = "sub_test_default",
    session_id: str = "cs_test_default",
) -> dict[str, Any]:
    """A real ``checkout.session.completed`` data.object.

    This is the one object type that legitimately carries
    ``client_reference_id`` — the handler sets it at checkout.
    """
    return {
        "id": session_id,
        "object": "checkout.session",
        "amount_subtotal": 1900,
        "amount_total": 1900,
        "client_reference_id": user_id,
        "currency": "usd",
        "customer": customer,
        "customer_details": {"email": "customer@example.com"},
        "livemode": False,
        "metadata": {},
        "mode": "subscription",
        "payment_status": "paid",
        "status": "complete",
        "subscription": subscription,
        "success_url": "https://example.com/success",
    }


def subscription(
    *,
    subscription_id: str,
    customer: str,
    status: str = "active",
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    """A real ``customer.subscription.*`` data.object.

    ``metadata`` defaults to ``{}`` — what Stripe sends for every
    subscription created before ``subscription_data.metadata`` was set at
    checkout. Pass a metadata dict only to model a post-fix subscription.
    """
    return {
        "id": subscription_id,
        "object": "subscription",
        "application": None,
        "cancel_at_period_end": False,
        "canceled_at": 1678145734 if status == "canceled" else None,
        "cancellation_details": {
            "comment": None,
            "feedback": None,
            "reason": "cancellation_requested" if status == "canceled" else None,
        },
        "collection_method": "charge_automatically",
        "created": 1679609767,
        "currency": "usd",
        "current_period_end": 1682288167,
        "current_period_start": 1679609767,
        "customer": customer,
        "items": {
            "object": "list",
            "data": [
                {
                    "id": "si_test_item",
                    "object": "subscription_item",
                    "price": {
                        "id": "price_test",
                        "object": "price",
                        "currency": "usd",
                        "recurring": {"interval": "month", "interval_count": 1},
                        "unit_amount": 1900,
                    },
                    "quantity": 1,
                    "subscription": subscription_id,
                }
            ],
        },
        "latest_invoice": "in_test_latest",
        "livemode": False,
        "metadata": metadata if metadata is not None else {},
        "start_date": 1679609767,
        "status": status,
    }


def invoice(
    *,
    customer: str,
    subscription_id: str = "sub_test_default",
    invoice_id: str = "in_test_default",
    status: str = "open",
) -> dict[str, Any]:
    """A real ``invoice.payment_failed`` data.object.

    Like subscriptions, invoices carry no ``client_reference_id`` and an
    empty ``metadata`` unless something explicitly set it.
    """
    return {
        "id": invoice_id,
        "object": "invoice",
        "amount_due": 1900,
        "amount_paid": 0,
        "attempt_count": 1,
        "attempted": True,
        "billing_reason": "subscription_cycle",
        "collection_method": "charge_automatically",
        "currency": "usd",
        "customer": customer,
        "customer_email": "customer@example.com",
        "livemode": False,
        "metadata": {},
        "paid": False,
        "status": status,
        "subscription": subscription_id,
        "total": 1900,
    }
