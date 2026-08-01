"""POST /stripe/webhook handler.

Verifies Stripe signatures against the raw request body, deduplicates on the
Stripe event id (delivery is at-least-once), and dispatches to handlers that
update the users table.
"""

from __future__ import annotations

import base64
import traceback
from typing import Any

import stripe

import config
from billing.stripe_client import get_stripe
from notifications import sender as email_sender
from notifications import templates as email_templates
from users.repository import UserRepository
from utils.http import json_response
from utils.logger import StructuredLogger


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return json_response(status, body)


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


def _user_id_from_object(obj: dict[str, Any], repo: UserRepository) -> str | None:
    """Resolve the userId (Cognito sub) from a Stripe object.

    Three paths, in order of reliability:

    1. ``client_reference_id`` — Checkout Sessions only. Does not exist on
       Subscription or Invoice objects.
    2. ``metadata.userId`` — set via ``subscription_data.metadata`` at
       checkout, so present only on subscriptions created after that was
       added (see ``billing.checkout.handle_billing_checkout``).
    3. ``customer`` → ``StripeCustomerIndex`` reverse lookup — the only
       identifier every relevant event carries, and the sole path that
       works for subscriptions predating (2).

    Returns None only when all three miss, which the caller must treat as
    an error rather than a silent no-op.
    """
    ref = obj.get("client_reference_id")
    if ref:
        return ref
    metadata = obj.get("metadata") or {}
    user_id = metadata.get("userId")
    if user_id:
        return user_id
    customer_id = obj.get("customer")
    if customer_id:
        user = repo.get_user_by_stripe_customer_id(customer_id)
        if user:
            return str(user["userId"])
    return None


def _unresolved(obj: dict[str, Any], event_type: str) -> None:
    """Log a resolution failure loudly.

    A silent return here is exactly how cancellations were lost: Stripe sees
    HTTP 200, the operator sees nothing, and the user keeps paid access.
    """
    StructuredLogger.error(
        f"Webhook {event_type}: could not resolve userId — event ignored",
        stripe_object_id=obj.get("id"),
        stripe_customer_id=obj.get("customer"),
        event_type=event_type,
    )


def _billing_period(obj: dict[str, Any]) -> tuple[int | None, int | None]:
    """Extract (period_start, period_end) from a Stripe subscription.

    Reads the flat fields first, then falls back to the subscription's items.
    Recent Stripe API versions moved ``current_period_start``/``end`` off the
    Subscription object and onto each SubscriptionItem, so which shape arrives
    depends on the API version the account is pinned to. Reading only one
    would fail soft — the field is skipped, quota quietly falls back to a
    fixed window, and Stripe-anchored renewal silently never happens.
    """
    start = obj.get("current_period_start")
    end = obj.get("current_period_end")
    if not end:
        # Normalise before indexing: a webhook payload is untrusted input, and
        # `items` arriving as a list or string would otherwise raise on .get()
        # and turn a malformed event into a 500 that Stripe then retries.
        raw_items = obj.get("items")
        items = raw_items.get("data") or [] if isinstance(raw_items, dict) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            start = start or item.get("current_period_start")
            end = item.get("current_period_end")
            if end:
                break
    return (int(start) if start else None, int(end) if end else None)


def _stale(user_id: str, event_type: str, event_created: int | None) -> None:
    """Log a transition refused for being older than the applied state.

    Not an error: Stripe does not order distinct events, so this is the
    control working. Logged at INFO because a sudden run of them means
    deliveries are arriving badly out of order and is worth seeing.
    """
    StructuredLogger.info(
        f"Webhook {event_type}: older than the last applied event — ignored",
        userId=user_id,
        event_type=event_type,
        eventCreated=event_created,
    )


# Checkout states that qualify for paid access.
#
# ``paid`` is the ordinary card outcome. ``no_payment_required`` is what
# Stripe reports for a full-coupon or trial subscription, which is a real
# customer with a real subscription — checking only for ``paid`` would refuse
# them. Everything else, notably ``unpaid``, does not qualify.
_PAID_CHECKOUT_STATES = frozenset({"paid", "no_payment_required"})


def _checkout_qualifies(obj: dict[str, Any], event_type: str) -> bool:
    """Whether a Checkout Session has actually bought the paid tier.

    ``checkout.session.completed`` fires when the *session* finishes, which
    is not the same as the customer having paid. A delayed payment method
    (ACH debit, bank transfer, some wallets) completes the session with
    ``payment_status="unpaid"`` and settles minutes-to-days later — or never.
    Granting on completion alone hands out the product before payment, and on
    a failed settlement, without it. The settlement is delivered separately as
    ``checkout.session.async_payment_succeeded``, which is in ``_DISPATCH``
    and passes through this same gate.

    A Stripe signature proves the event is authentic; it says nothing about
    whether this particular state qualifies for entitlement. That is what
    this checks.

    ``mode`` is checked because ``handle_billing_checkout`` creates
    subscription-mode sessions and nothing else: a payment-mode session here
    would price a subscription at a single payment. The configured price is
    bound at session creation for the same reason — the webhook payload does
    not carry ``line_items`` unless expanded, so creation is the only place
    that binding can be made.
    """
    mode = obj.get("mode")
    payment_status = obj.get("payment_status")
    status = obj.get("status")
    if (
        mode != "subscription"
        or payment_status not in _PAID_CHECKOUT_STATES
        or status != "complete"
    ):
        StructuredLogger.warning(
            f"Webhook {event_type}: checkout does not qualify for paid access — ignored",
            stripe_object_id=obj.get("id"),
            mode=mode,
            paymentStatus=payment_status,
            sessionStatus=status,
        )
        return False
    return True


def _on_checkout_completed(
    obj: dict[str, Any], repo: UserRepository, event_type: str, event_created: int | None
) -> None:
    user_id = _user_id_from_object(obj, repo)
    if not user_id:
        _unresolved(obj, event_type)
        return
    if not _checkout_qualifies(obj, event_type):
        return
    # Facts first, unconditionally: a late event still knows the customer id.
    repo.record_billing_facts(
        user_id,
        stripeCustomerId=obj.get("customer"),
        stripeSubscriptionId=obj.get("subscription"),
    )
    if not repo.set_tier(
        user_id,
        "paid",
        event_created=event_created,
        subscriptionStatus="active",
    ):
        _stale(user_id, event_type, event_created)
    # Outside the guard on purpose. The watermark answers "is this the newest
    # word on the tier"; it does not answer "did this purchase happen". It
    # did — the event is signed and `claim_webhook_event` has already
    # guaranteed it is applied exactly once, which is the property these two
    # need. Gating them on the tier write instead meant a checkout that lost a
    # race to its own customer.subscription.created silently never counted the
    # subscriber and never sent the welcome email, while the eventual
    # cancellation still decremented — so activeSubscribers drifted negative
    # across ordinary subscribe/cancel cycles.
    repo.increment_revenue_counter("activeSubscribers", 1)
    _send_lifecycle_email(repo, user_id, email_templates.welcome_email)


def _on_subscription_upsert(
    obj: dict[str, Any], repo: UserRepository, event_type: str, event_created: int | None
) -> None:
    user_id = _user_id_from_object(obj, repo)
    if not user_id:
        _unresolved(obj, event_type)
        return
    status = obj.get("status", "active")
    tier = "paid" if status in ("active", "trialing") else "free"
    # Credit allotments renew on Stripe's own period boundary, not a fixed
    # 30-day clock: Stripe's monthly cycles run 28-31 days, so a fixed window
    # would grant credits before the customer is billed in some months and
    # leave them short after renewal in others.
    period_start, period_end = _billing_period(obj)
    if not period_end:
        # Not fatal — quota falls back to a fixed window — but it silently
        # means paid users never get Stripe-anchored renewal, so say so.
        StructuredLogger.warning(
            "Subscription carried no billing period; credit renewal will "
            "fall back to a fixed window",
            stripe_subscription_id=obj.get("id"),
        )
    # Unconditional: these are what Stripe reported, not a transition. This
    # event is the ONLY source of the billing period, so letting the ordering
    # guard discard it left paying customers renewing on the fixed fallback
    # clock — and the warning above fires before the rejected write, so the
    # operator saw nothing.
    repo.record_billing_facts(
        user_id,
        stripeCustomerId=obj.get("customer"),
        stripeCurrentPeriodEnd=period_end,
        stripeCurrentPeriodStart=period_start,
    )
    if not repo.set_tier(
        user_id,
        tier,
        event_created=event_created,
        subscriptionStatus=status,
        stripeSubscriptionId=obj.get("id", ""),
    ):
        _stale(user_id, event_type, event_created)
        return
    if status == "active":
        _send_lifecycle_email(repo, user_id, email_templates.subscription_activated_email)


def _on_subscription_deleted(
    obj: dict[str, Any], repo: UserRepository, event_type: str, event_created: int | None
) -> None:
    user_id = _user_id_from_object(obj, repo)
    if not user_id:
        _unresolved(obj, event_type)
        return
    if not repo.set_tier(
        user_id,
        "free",
        event_created=event_created,
        subscriptionStatus="canceled",
        stripeSubscriptionId="",
    ):
        _stale(user_id, event_type, event_created)
    # Outside the guard, and it must pair with the increment in
    # _on_checkout_completed: gating one on the ordering watermark and not the
    # other is what makes activeSubscribers drift. The cancellation happened
    # whatever order it arrived in, and dedup already bounds it to once.
    #
    # One atomic UpdateItem, not two sequential ones: a failure between
    # them would release the idempotency claim with the first delta already
    # applied, and Stripe's retry would apply it a second time.
    repo.apply_revenue_deltas({"activeSubscribers": -1, "monthlyChurn": 1})
    _send_lifecycle_email(repo, user_id, email_templates.subscription_cancelled_email)


def _on_payment_failed(
    obj: dict[str, Any], repo: UserRepository, event_type: str, event_created: int | None
) -> None:
    user_id = _user_id_from_object(obj, repo)
    if not user_id:
        _unresolved(obj, event_type)
        return
    user = repo.get_user(user_id)
    if user is None:
        return
    current_tier = user.get("tier", "free")
    # Keep tier as-is; only mark status as past_due.
    if not repo.set_tier(
        user_id, current_tier, event_created=event_created, subscriptionStatus="past_due"
    ):
        _stale(user_id, event_type, event_created)
    # Outside the guard. A declined renewal routinely emits
    # customer.subscription.updated (status=past_due) a second AFTER the
    # invoice event that caused it, and Stripe delivers them concurrently — so
    # the subscription event commonly wins the watermark and this one reads as
    # stale. The payment still failed. Gating the warning on the write meant
    # the customer was never told their card was declined and simply lost
    # access when Stripe's dunning retries ran out.
    _send_lifecycle_email(repo, user_id, email_templates.payment_failed_email)


_DISPATCH = {
    "checkout.session.completed": _on_checkout_completed,
    # A delayed payment method settling. Refusing the unpaid completion above
    # is only correct if the customer still gets what they bought once the
    # payment clears, and this is the event that says it did. The matching
    # failure event is deliberately absent: there is nothing to revoke,
    # because nothing was granted.
    "checkout.session.async_payment_succeeded": _on_checkout_completed,
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
    # Subscript, not .get(): StripeObject's custom __getattr__ raises
    # AttributeError for dict methods it doesn't define.
    try:
        event_id = str(stripe_event["id"] or "")
    except (KeyError, AttributeError):
        event_id = ""
    # When Stripe generated the event, which is not the order it arrives in.
    # None disables the monotonic guard for this event rather than treating a
    # missing timestamp as "older than everything", which would silently drop
    # every event from an account whose payloads omit it.
    try:
        event_created: int | None = int(stripe_event["created"])
    except (KeyError, AttributeError, TypeError, ValueError):
        event_created = None
    handler = _DISPATCH.get(event_type)
    if handler:
        # Stripe delivers at-least-once. Claim the event id before mutating
        # anything so a redelivery cannot double-count revenue counters.
        try:
            claimed = repo.claim_webhook_event(event_id)
        except Exception as e:
            StructuredLogger.error(
                f"Webhook dedup claim failed for {event_id}: {e}",
                correlation_id=correlation_id,
                traceback=traceback.format_exc(),
            )
            # Fail closed: let Stripe retry rather than risk a double-apply.
            return _response(500, {"error": "dedup unavailable"})
        if not claimed:
            StructuredLogger.info(
                f"Webhook {event_type} {event_id} already processed — skipping",
                correlation_id=correlation_id,
            )
            return _response(200, {"received": True, "duplicate": True})
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
            handler(obj, repo, event_type, event_created)
            # Only a completed record suppresses redelivery. Until this lands
            # the claim is just a lease, so a crash mid-handler is retried.
            repo.complete_webhook_event(event_id)
        except Exception as e:
            StructuredLogger.error(
                f"Webhook handler error for {event_type}: {e}",
                correlation_id=correlation_id,
                traceback=traceback.format_exc(),
            )
            # Release the claim so Stripe's retry can re-process. Holding it
            # would turn one transient failure into a permanently dropped
            # event — for a cancellation, that is paid access kept forever.
            try:
                repo.release_webhook_event(event_id)
            except Exception as release_err:
                StructuredLogger.error(
                    f"Failed to release dedup claim for {event_id}: {release_err}",
                    correlation_id=correlation_id,
                )
            return _response(500, {"error": "handler failed"})
    return _response(200, {"received": True})
