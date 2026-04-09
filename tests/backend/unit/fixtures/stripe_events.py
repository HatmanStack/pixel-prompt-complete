"""Helpers to build signed Stripe webhook payloads for tests."""

from __future__ import annotations

import hmac
import json
import time
from hashlib import sha256
from typing import Any


def sign_payload(payload: str, secret: str, timestamp: int | None = None) -> str:
    """Return a Stripe-Signature header for ``payload``.

    Mirrors ``stripe.WebhookSignature``'s v1 scheme: ``t=<ts>,v1=<hmac>``.
    """
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.{payload}".encode()
    sig = hmac.new(secret.encode(), signed_payload, sha256).hexdigest()
    return f"t={ts},v1={sig}"


def build_event(event_type: str, obj: dict[str, Any], event_id: str = "evt_1") -> str:
    """Return a JSON-encoded Stripe event payload."""
    return json.dumps(
        {
            "id": event_id,
            "object": "event",
            "type": event_type,
            "data": {"object": obj},
        }
    )
