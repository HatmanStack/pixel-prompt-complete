"""Tests for POST /stripe/webhook.

These tests use **unmodified, real-shaped Stripe payloads**. Subscription and
invoice objects carry ``metadata: {}`` and no ``client_reference_id``, because
that is what Stripe actually sends. An earlier version of this suite
hand-injected ``metadata: {"userId": ...}`` into those objects, which made a
broken cancellation path look green — see ``test_no_fixture_injects_user_id``,
which exists to stop that regressing.

A user is resolved from a subscription/invoice event via the
``StripeCustomerIndex`` reverse lookup on ``stripeCustomerId``. That is the
only path real traffic can take for subscriptions created before
``subscription_data.metadata`` was added at checkout.
"""

from __future__ import annotations

import base64
import importlib
import json
import os

import boto3
import pytest
from moto import mock_aws

from .fixtures import stripe_events
from .fixtures.stripe_events import (
    build_event,
    checkout_session,
    invoice,
    sign_payload,
    subscription,
)

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

WEBHOOK_SECRET = "whsec_test_123"
TABLE_NAME = "pixel-prompt-users-webhook"


@pytest.fixture
def billing_on(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("BILLING_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "secret")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("USERS_TABLE_NAME", TABLE_NAME)
    import config

    importlib.reload(config)
    from billing import stripe_client

    stripe_client.reset_stripe_client()
    yield
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    importlib.reload(config)
    stripe_client.reset_stripe_client()


@pytest.fixture
def wired(billing_on):
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        try:
            ddb.create_table(
                TableName=TABLE_NAME,
                KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
                AttributeDefinitions=[
                    {"AttributeName": "userId", "AttributeType": "S"},
                    {"AttributeName": "stripeCustomerId", "AttributeType": "S"},
                ],
                GlobalSecondaryIndexes=[
                    {
                        "IndexName": "StripeCustomerIndex",
                        "KeySchema": [
                            {"AttributeName": "stripeCustomerId", "KeyType": "HASH"}
                        ],
                        "Projection": {"ProjectionType": "KEYS_ONLY"},
                    }
                ],
                BillingMode="PAY_PER_REQUEST",
            )
        except Exception:
            pass
        table = ddb.Table(TABLE_NAME)
        scan = table.scan()
        for item in scan.get("Items", []):
            table.delete_item(Key={"userId": item["userId"]})
        import lambda_function

        importlib.reload(lambda_function)
        from users.repository import UserRepository

        lambda_function._user_repo = UserRepository(TABLE_NAME, dynamodb_resource=ddb)
        yield lambda_function


def _event(body: str, sig: str | None = None, b64: bool = False) -> dict:
    headers = {}
    if sig is not None:
        headers["Stripe-Signature"] = sig
    body_field = base64.b64encode(body.encode()).decode() if b64 else body
    return {
        "rawPath": "/stripe/webhook",
        "requestContext": {"http": {"method": "POST", "sourceIp": "1.2.3.4"}},
        "headers": headers,
        "body": body_field,
        "isBase64Encoded": b64,
    }


def _send(wired, payload: str, *, sign: bool = True, b64: bool = False):
    sig = sign_payload(payload, WEBHOOK_SECRET) if sign else "t=1,v1=deadbeef"
    return wired.lambda_handler(_event(payload, sig=sig, b64=b64), None)


def _body(r):
    return json.loads(r["body"])


def _seed_subscriber(wired, user_id: str, customer: str, **extra):
    """Create a user who has completed checkout (so the GSI can find them)."""
    wired._user_repo.get_or_create_user(user_id, email=extra.pop("email", None))
    wired._user_repo.set_tier(
        user_id,
        extra.pop("tier", "paid"),
        stripeCustomerId=customer,
        **extra,
    )


# ---- Fixture integrity ----


def test_no_fixture_injects_user_id():
    """Guard: subscription/invoice fixtures must never carry metadata.userId.

    Hand-injecting that key is what concealed the cancellation bug. If this
    fails, the suite has drifted back to testing a payload Stripe never sends.
    """
    sub = subscription(subscription_id="sub_x", customer="cus_x")
    inv = invoice(customer="cus_x")
    assert sub["metadata"] == {}
    assert inv["metadata"] == {}
    assert "client_reference_id" not in sub
    assert "client_reference_id" not in inv


# ---- Signature / config gates ----


def test_flags_off_returns_501(monkeypatch):
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    monkeypatch.setenv("AUTH_ENABLED", "false")
    import config

    importlib.reload(config)
    import lambda_function

    importlib.reload(lambda_function)
    r = lambda_function.lambda_handler(_event("{}", sig="t=1,v1=x"), None)
    assert r["statusCode"] == 501


def test_missing_signature_returns_400(wired):
    r = wired.lambda_handler(_event("{}"), None)
    assert r["statusCode"] == 400


def test_bad_signature_returns_400(wired):
    payload = build_event(
        "checkout.session.completed",
        checkout_session(user_id="u1", customer="cus_1"),
    )
    r = _send(wired, payload, sign=False)
    assert r["statusCode"] == 400


def test_invalid_payload_returns_400(wired):
    from billing import webhook as wh

    def raise_value(*a, **k):
        raise ValueError("not json")

    orig = wh.stripe.Webhook.construct_event
    wh.stripe.Webhook.construct_event = raise_value
    try:
        r = wired.lambda_handler(
            _event("{}", sig=sign_payload("{}", WEBHOOK_SECRET)), None
        )
    finally:
        wh.stripe.Webhook.construct_event = orig
    assert r["statusCode"] == 400


def test_stripe_not_configured_returns_500(wired, monkeypatch):
    import config as cfg
    from billing import stripe_client

    monkeypatch.setattr(cfg, "stripe_secret_key", "")
    stripe_client.reset_stripe_client()
    payload = build_event(
        "checkout.session.completed",
        checkout_session(user_id="u", customer="cus_u"),
    )
    r = _send(wired, payload)
    assert r["statusCode"] == 500


def test_base64_body_verified_correctly(wired):
    wired._user_repo.get_or_create_user("u6")
    payload = build_event(
        "checkout.session.completed",
        checkout_session(user_id="u6", customer="cus_6", subscription="sub_6"),
    )
    r = _send(wired, payload, b64=True)
    assert r["statusCode"] == 200
    assert wired._user_repo.get_user("u6")["tier"] == "paid"


def test_unknown_event_type_returns_200_noop(wired):
    payload = build_event("customer.updated", {"id": "cus_x", "object": "customer"})
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    assert _body(r)["received"] is True


# ---- Checkout: the one object that carries client_reference_id ----


def test_checkout_session_completed_sets_paid(wired):
    wired._user_repo.get_or_create_user("u1", email="u@x.com")
    payload = build_event(
        "checkout.session.completed",
        checkout_session(user_id="u1", customer="cus_1", subscription="sub_1"),
    )
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    item = wired._user_repo.get_user("u1")
    assert item["tier"] == "paid"
    assert item["stripeCustomerId"] == "cus_1"
    assert item["stripeSubscriptionId"] == "sub_1"
    assert item["subscriptionStatus"] == "active"


# ---- REGRESSION: real cancellation payloads must downgrade ----


def test_real_subscription_deleted_downgrades_to_free(wired):
    """The bug this suite previously concealed.

    A real customer.subscription.deleted carries no client_reference_id and
    empty metadata. Resolution must fall through to the customer reverse
    lookup, or the churned user keeps paid access forever.
    """
    _seed_subscriber(
        wired,
        "u3",
        "cus_3",
        stripeSubscriptionId="sub_3",
        subscriptionStatus="active",
    )
    payload = build_event(
        "customer.subscription.deleted",
        subscription(subscription_id="sub_3", customer="cus_3", status="canceled"),
    )
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    item = wired._user_repo.get_user("u3")
    assert item["tier"] == "free"
    assert item["subscriptionStatus"] == "canceled"


def test_real_subscription_updated_syncs_status(wired):
    _seed_subscriber(wired, "u2", "cus_2")
    payload = build_event(
        "customer.subscription.updated",
        subscription(subscription_id="sub_2", customer="cus_2", status="active"),
    )
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    item = wired._user_repo.get_user("u2")
    assert item["tier"] == "paid"
    assert item["subscriptionStatus"] == "active"
    assert item["stripeSubscriptionId"] == "sub_2"


def test_real_subscription_canceled_status_downgrades(wired):
    _seed_subscriber(wired, "u8", "cus_8")
    payload = build_event(
        "customer.subscription.updated",
        subscription(subscription_id="sub_8", customer="cus_8", status="canceled"),
    )
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    assert wired._user_repo.get_user("u8")["tier"] == "free"


def test_real_invoice_payment_failed_marks_past_due_but_keeps_paid(wired):
    _seed_subscriber(wired, "u4", "cus_4")
    payload = build_event("invoice.payment_failed", invoice(customer="cus_4"))
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    item = wired._user_repo.get_user("u4")
    assert item["tier"] == "paid"
    assert item["subscriptionStatus"] == "past_due"


def test_post_fix_subscription_metadata_also_resolves(wired):
    """Forward path: subscriptions created after subscription_data.metadata
    was added carry metadata.userId and resolve without touching the GSI."""
    wired._user_repo.get_or_create_user("u_meta")
    payload = build_event(
        "customer.subscription.deleted",
        subscription(
            subscription_id="sub_meta",
            customer="cus_unknown_to_us",
            status="canceled",
            metadata={"userId": "u_meta"},
        ),
    )
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    assert wired._user_repo.get_user("u_meta")["tier"] == "free"


def test_unresolvable_event_is_noop_and_logged(wired):
    """No client_reference_id, no metadata, unknown customer -> no crash."""
    payload = build_event(
        "customer.subscription.deleted",
        subscription(subscription_id="sub_ghost", customer="cus_never_seen"),
    )
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    assert wired._user_repo.get_revenue().get("activeSubscribers", 0) == 0


# ---- Idempotency ----


def test_duplicate_event_applies_counters_exactly_once(wired):
    """Stripe delivers at-least-once. A redelivery must not double-count."""
    wired._user_repo.get_or_create_user("u5")
    payload = build_event(
        "checkout.session.completed",
        checkout_session(user_id="u5", customer="cus_5", subscription="sub_5"),
        event_id="evt_dup_fixed",
    )
    r1 = _send(wired, payload)
    r2 = _send(wired, payload)
    assert r1["statusCode"] == 200
    assert r2["statusCode"] == 200
    assert _body(r2).get("duplicate") is True
    assert wired._user_repo.get_user("u5")["tier"] == "paid"
    assert wired._user_repo.get_revenue().get("activeSubscribers", 0) == 1


def test_duplicate_cancellation_cannot_drive_subscribers_negative(wired):
    _seed_subscriber(wired, "u_neg", "cus_neg")
    wired._user_repo.increment_revenue_counter("activeSubscribers", 1)
    payload = build_event(
        "customer.subscription.deleted",
        subscription(subscription_id="sub_neg", customer="cus_neg", status="canceled"),
        event_id="evt_cancel_dup",
    )
    _send(wired, payload)
    _send(wired, payload)
    _send(wired, payload)
    revenue = wired._user_repo.get_revenue()
    assert revenue.get("activeSubscribers", 0) == 0
    assert revenue.get("monthlyChurn", 0) == 1


def test_distinct_event_ids_both_apply(wired):
    """Dedup must key on the event id, not the payload contents."""
    wired._user_repo.get_or_create_user("u_a")
    wired._user_repo.get_or_create_user("u_b")
    for uid, cus in (("u_a", "cus_a"), ("u_b", "cus_b")):
        _send(
            wired,
            build_event(
                "checkout.session.completed",
                checkout_session(user_id=uid, customer=cus),
            ),
        )
    assert wired._user_repo.get_revenue().get("activeSubscribers", 0) == 2


def test_handler_failure_releases_claim_so_retry_succeeds(wired, monkeypatch):
    """A transient failure must not permanently swallow the event."""
    from billing import webhook as wh

    wired._user_repo.get_or_create_user("u_retry")
    payload = build_event(
        "checkout.session.completed",
        checkout_session(user_id="u_retry", customer="cus_retry"),
        event_id="evt_retry",
    )

    calls = {"n": 0}
    real = wh._DISPATCH["checkout.session.completed"]

    def flaky(obj, repo, event_type, event_created):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return real(obj, repo, event_type, event_created)

    monkeypatch.setitem(wh._DISPATCH, "checkout.session.completed", flaky)

    first = _send(wired, payload)
    assert first["statusCode"] == 500

    # Stripe retries the same event id; the claim must have been released.
    second = _send(wired, payload)
    assert second["statusCode"] == 200
    assert wired._user_repo.get_user("u_retry")["tier"] == "paid"


def test_handler_exception_returns_500(wired, monkeypatch):
    from billing import webhook as wh

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setitem(wh._DISPATCH, "checkout.session.completed", boom)
    payload = build_event(
        "checkout.session.completed",
        checkout_session(user_id="u7", customer="cus_7"),
    )
    assert _send(wired, payload)["statusCode"] == 500


def test_partial_counter_failure_does_not_double_apply(wired, monkeypatch):
    """Revenue deltas must be atomic across a mid-handler failure.

    _on_subscription_deleted previously did two sequential ADD updates. If
    the first landed and the second threw, the idempotency claim was
    released and Stripe's retry re-applied the first — driving
    activeSubscribers negative, which is the very thing dedup exists to
    prevent, reached through a narrower window than full redelivery.
    """
    _seed_subscriber(wired, "u_partial", "cus_partial")
    wired._user_repo.increment_revenue_counter("activeSubscribers", 1)

    real = wired._user_repo.apply_revenue_deltas
    state = {"n": 0}

    def flaky_deltas(deltas):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("dynamo throttled on hot revenue# item")
        return real(deltas)

    monkeypatch.setattr(wired._user_repo, "apply_revenue_deltas", flaky_deltas)

    payload = build_event(
        "customer.subscription.deleted",
        subscription(subscription_id="sub_p", customer="cus_partial", status="canceled"),
        event_id="evt_partial",
    )
    assert _send(wired, payload)["statusCode"] == 500
    assert _send(wired, payload)["statusCode"] == 200

    revenue = wired._user_repo.get_revenue()
    assert revenue.get("activeSubscribers", 0) == 0
    assert revenue.get("monthlyChurn", 0) == 1
    assert wired._user_repo.get_user("u_partial")["tier"] == "free"


def test_apply_revenue_deltas_is_all_or_nothing(wired):
    """Both counters move in a single UpdateItem."""
    repo = wired._user_repo
    repo.increment_revenue_counter("activeSubscribers", 5)
    repo.apply_revenue_deltas({"activeSubscribers": -1, "monthlyChurn": 1})
    revenue = repo.get_revenue()
    assert revenue.get("activeSubscribers", 0) == 4
    assert revenue.get("monthlyChurn", 0) == 1


def test_apply_revenue_deltas_noop_on_empty(wired):
    wired._user_repo.apply_revenue_deltas({})
    assert wired._user_repo.get_revenue().get("activeSubscribers", 0) == 0


def test_unresolved_log_uses_the_real_event_type(wired, monkeypatch):
    """created vs updated must be distinguishable in the ERROR log."""
    from billing import webhook as wh

    seen: list[str] = []
    monkeypatch.setattr(wh, "_unresolved", lambda obj, event_type: seen.append(event_type))

    for event_type in ("customer.subscription.created", "customer.subscription.updated"):
        _send(
            wired,
            build_event(
                event_type,
                subscription(subscription_id="sub_ghost", customer="cus_never_seen"),
            ),
        )
    assert seen == ["customer.subscription.created", "customer.subscription.updated"]


def test_failed_release_does_not_lose_the_event_forever(wired, monkeypatch):
    """If release-on-failure itself fails, the lease must let a retry through.

    Without a lease the orphaned claim answers every Stripe retry with
    "duplicate" and the cancellation is lost permanently — the original bug,
    reintroduced by its own fix.
    """
    from billing import webhook as wh

    _seed_subscriber(wired, "u_orphan", "cus_orphan")
    payload = build_event(
        "customer.subscription.deleted",
        subscription(subscription_id="sub_orphan", customer="cus_orphan", status="canceled"),
        event_id="evt_orphan",
    )

    real = wh._DISPATCH["customer.subscription.deleted"]
    state = {"n": 0}

    def fails_once(obj, repo, event_type, event_created):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("handler blew up")
        return real(obj, repo, event_type, event_created)

    monkeypatch.setitem(wh._DISPATCH, "customer.subscription.deleted", fails_once)
    # Release also fails, orphaning the claim.
    monkeypatch.setattr(
        wired._user_repo,
        "release_webhook_event",
        lambda event_id: (_ for _ in ()).throw(RuntimeError("delete failed")),
    )

    assert _send(wired, payload)["statusCode"] == 500
    assert wired._user_repo.get_user("u_orphan")["tier"] == "paid"

    # Immediately after, the lease is still held: retry is correctly suppressed.
    assert _body(_send(wired, payload)).get("duplicate") is True

    # Once the lease lapses, Stripe's retry gets through and the user downgrades.
    import time as _time

    wired._user_repo._table.update_item(
        Key={"userId": "event#evt_orphan"},
        UpdateExpression="SET leaseExpiresAt = :past",
        ExpressionAttributeValues={":past": int(_time.time()) - 1},
    )
    assert _send(wired, payload)["statusCode"] == 200
    assert wired._user_repo.get_user("u_orphan")["tier"] == "free"


def test_completed_event_is_never_reclaimed(wired):
    """A completed record blocks redelivery even past the lease window."""
    import time as _time

    wired._user_repo.get_or_create_user("u_done")
    payload = build_event(
        "checkout.session.completed",
        checkout_session(user_id="u_done", customer="cus_done"),
        event_id="evt_done",
    )
    assert _send(wired, payload)["statusCode"] == 200

    marker = wired._user_repo.get_user("event#evt_done")
    assert marker is not None
    assert "completedAt" in marker
    assert "leaseExpiresAt" not in marker

    # Even with an expired lease attribute forced back on, completion wins.
    wired._user_repo._table.update_item(
        Key={"userId": "event#evt_done"},
        UpdateExpression="SET leaseExpiresAt = :past",
        ExpressionAttributeValues={":past": int(_time.time()) - 1},
    )
    assert _body(_send(wired, payload)).get("duplicate") is True
    assert wired._user_repo.get_revenue().get("activeSubscribers", 0) == 1


def test_dedup_store_failure_fails_closed(wired, monkeypatch):
    """If the dedup claim cannot be taken, prefer a retry over a double-apply."""

    def boom(*a, **k):
        raise RuntimeError("dynamo down")

    monkeypatch.setattr(wired._user_repo, "claim_webhook_event", boom)
    payload = build_event(
        "checkout.session.completed",
        checkout_session(user_id="u_fc", customer="cus_fc"),
    )
    assert _send(wired, payload)["statusCode"] == 500


# ---- Email notifications ----


def _capture_emails(monkeypatch):
    from notifications import sender

    calls: list[dict] = []

    def mock_send(to, subject, html, text):
        calls.append({"to": to, "subject": subject})
        return True

    monkeypatch.setattr(sender, "send_email", mock_send)
    return calls


def test_checkout_completed_sends_welcome_email(wired, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg, "ses_enabled", True)
    wired._user_repo.get_or_create_user("u_email1", email="user1@example.com")
    calls = _capture_emails(monkeypatch)
    payload = build_event(
        "checkout.session.completed",
        checkout_session(user_id="u_email1", customer="cus_e1"),
    )
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    assert len(calls) == 1
    assert calls[0]["to"] == "user1@example.com"
    assert "Welcome" in calls[0]["subject"]


def test_subscription_deleted_sends_cancellation_email(wired, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg, "ses_enabled", True)
    _seed_subscriber(
        wired,
        "u_email2",
        "cus_e2",
        email="user2@example.com",
        subscriptionStatus="active",
    )
    calls = _capture_emails(monkeypatch)
    payload = build_event(
        "customer.subscription.deleted",
        subscription(subscription_id="sub_e2", customer="cus_e2", status="canceled"),
    )
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    assert len(calls) == 1
    assert calls[0]["to"] == "user2@example.com"
    assert "Cancel" in calls[0]["subject"]


def test_payment_failed_sends_warning_email(wired, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg, "ses_enabled", True)
    _seed_subscriber(wired, "u_email3", "cus_e3", email="user3@example.com")
    calls = _capture_emails(monkeypatch)
    r = _send(wired, build_event("invoice.payment_failed", invoice(customer="cus_e3")))
    assert r["statusCode"] == 200
    assert len(calls) == 1
    assert calls[0]["to"] == "user3@example.com"
    assert "Payment" in calls[0]["subject"]


def test_subscription_upsert_active_sends_activated_email(wired, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg, "ses_enabled", True)
    _seed_subscriber(wired, "u_email_act", "cus_act", email="activated@example.com")
    calls = _capture_emails(monkeypatch)
    payload = build_event(
        "customer.subscription.updated",
        subscription(subscription_id="sub_act", customer="cus_act", status="active"),
    )
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    assert len(calls) == 1
    assert calls[0]["to"] == "activated@example.com"
    assert "Active" in calls[0]["subject"]


def test_subscription_upsert_non_active_skips_email(wired, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg, "ses_enabled", True)
    _seed_subscriber(wired, "u_email_noact", "cus_noact", email="noact@example.com")
    calls = _capture_emails(monkeypatch)
    payload = build_event(
        "customer.subscription.updated",
        subscription(
            subscription_id="sub_noact", customer="cus_noact", status="past_due"
        ),
    )
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    assert len(calls) == 0


def test_no_email_when_user_has_no_email(wired, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg, "ses_enabled", True)
    wired._user_repo.get_or_create_user("u_email5")
    calls = _capture_emails(monkeypatch)
    payload = build_event(
        "checkout.session.completed",
        checkout_session(user_id="u_email5", customer="cus_e5"),
    )
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    assert len(calls) == 0


def test_webhook_returns_200_when_email_fails(wired, monkeypatch):
    """Email is fire-and-forget: an SES failure must not fail the webhook."""
    import config as cfg
    from notifications import sender

    monkeypatch.setattr(cfg, "ses_enabled", True)
    wired._user_repo.get_or_create_user("u_email6", email="user6@example.com")

    def exploding_send(to, subject, html, text):
        raise RuntimeError("SES exploded")

    monkeypatch.setattr(sender, "send_email", exploding_send)
    payload = build_event(
        "checkout.session.completed",
        checkout_session(user_id="u_email6", customer="cus_e6"),
    )
    assert _send(wired, payload)["statusCode"] == 200


# ---- Revenue counters ----


def test_checkout_completed_increments_active_subscribers(wired):
    wired._user_repo.get_or_create_user("u_rev1")
    payload = build_event(
        "checkout.session.completed",
        checkout_session(user_id="u_rev1", customer="cus_r1"),
    )
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    assert wired._user_repo.get_revenue().get("activeSubscribers", 0) == 1


def test_real_subscription_deleted_decrements_and_churns(wired):
    _seed_subscriber(wired, "u_rev2", "cus_r2")
    wired._user_repo.increment_revenue_counter("activeSubscribers", 1)
    payload = build_event(
        "customer.subscription.deleted",
        subscription(subscription_id="sub_r2", customer="cus_r2", status="canceled"),
    )
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    revenue = wired._user_repo.get_revenue()
    assert revenue.get("activeSubscribers", 0) == 0
    assert revenue.get("monthlyChurn", 0) == 1


# ---- Reverse lookup unit coverage ----


def test_reverse_lookup_returns_none_for_unknown_customer(wired):
    assert wired._user_repo.get_user_by_stripe_customer_id("cus_nope") is None


def test_reverse_lookup_returns_none_for_empty_customer(wired):
    assert wired._user_repo.get_user_by_stripe_customer_id("") is None


def test_reverse_lookup_finds_seeded_subscriber(wired):
    _seed_subscriber(wired, "u_lookup", "cus_lookup")
    found = wired._user_repo.get_user_by_stripe_customer_id("cus_lookup")
    assert found is not None
    assert found["userId"] == "u_lookup"


def test_event_ids_are_unique_by_default():
    """build_event must not reuse ids, or tests silently dedup each other."""
    a = json.loads(build_event("customer.updated", {}))
    b = json.loads(build_event("customer.updated", {}))
    assert a["id"] != b["id"]
    assert stripe_events is not None


# ---- Billing period extraction (drives credit renewal) ----


def test_billing_period_read_from_flat_subscription_fields(wired):
    """Older Stripe API shape: period lives on the Subscription object."""
    _seed_subscriber(wired, "u_perflat", "cus_perflat")
    obj = subscription(subscription_id="sub_pf", customer="cus_perflat")
    obj["current_period_start"] = 1679609767
    obj["current_period_end"] = 1682288167

    _send(wired, build_event("customer.subscription.updated", obj))

    user = wired._user_repo.get_user("u_perflat")
    assert int(user["stripeCurrentPeriodEnd"]) == 1682288167
    assert int(user["stripeCurrentPeriodStart"]) == 1679609767


def test_billing_period_falls_back_to_subscription_items(wired):
    """Newer Stripe API shape moved the period onto SubscriptionItem.

    Reading only the flat field would fail soft: the attribute is skipped,
    quota quietly falls back to a fixed window, and Stripe-anchored credit
    renewal silently never happens for anyone.
    """
    _seed_subscriber(wired, "u_peritem", "cus_peritem")
    obj = subscription(subscription_id="sub_pi", customer="cus_peritem")
    obj.pop("current_period_start", None)
    obj.pop("current_period_end", None)
    obj["items"]["data"][0]["current_period_start"] = 1700000000
    obj["items"]["data"][0]["current_period_end"] = 1702592000

    _send(wired, build_event("customer.subscription.updated", obj))

    user = wired._user_repo.get_user("u_peritem")
    assert int(user["stripeCurrentPeriodEnd"]) == 1702592000
    assert int(user["stripeCurrentPeriodStart"]) == 1700000000


def test_missing_billing_period_is_survivable(wired):
    """No period anywhere must not fail the webhook — quota falls back."""
    _seed_subscriber(wired, "u_pernone", "cus_pernone")
    obj = subscription(subscription_id="sub_pn", customer="cus_pernone")
    obj.pop("current_period_start", None)
    obj.pop("current_period_end", None)

    resp = _send(wired, build_event("customer.subscription.updated", obj))

    assert resp["statusCode"] == 200
    user = wired._user_repo.get_user("u_pernone")
    assert user["tier"] == "paid"
    assert "stripeCurrentPeriodEnd" not in user


def test_billing_period_helper_handles_malformed_items():
    """Malformed payloads must degrade, not 500.

    A webhook body is untrusted input. An exception here becomes a 500, which
    Stripe then retries — so a single malformed event would loop rather than
    being ignored.
    """
    from billing.webhook import _billing_period

    assert _billing_period({}) == (None, None)
    assert _billing_period({"items": {}}) == (None, None)
    assert _billing_period({"items": {"data": ["nonsense", None]}}) == (None, None)
    # `items` arriving as the wrong type entirely.
    assert _billing_period({"items": []}) == (None, None)
    assert _billing_period({"items": [{"current_period_end": 1}]}) == (None, None)
    assert _billing_period({"items": "nope"}) == (None, None)
    assert _billing_period({"items": None}) == (None, None)


def test_malformed_items_does_not_500_the_webhook(wired):
    """End to end: a bad `items` shape must still return 200."""
    _seed_subscriber(wired, "u_malformed", "cus_malformed")
    obj = subscription(subscription_id="sub_mf", customer="cus_malformed")
    obj.pop("current_period_end", None)
    obj["items"] = "not-a-dict"

    resp = _send(wired, build_event("customer.subscription.updated", obj))
    assert resp["statusCode"] == 200
    assert wired._user_repo.get_user("u_malformed")["tier"] == "paid"


# ---- Event ordering: Stripe guarantees delivery, not order ----
#
# Signature verification proves an event is authentic and the dedup claim
# stops one event id being applied twice. Neither orders two *distinct*
# authentic events, so a subscription update generated before a cancellation
# but delivered after it used to overwrite the cancellation and hand paid
# access back.


def test_stale_subscription_update_cannot_resurrect_paid(wired):
    """The finding: an older active update delivered after a cancellation.

    Both events are genuinely signed and carry distinct ids, so neither
    signature verification nor dedup rejects them. Only the recorded
    high-water mark can.
    """
    _seed_subscriber(
        wired,
        "u_order",
        "cus_order",
        stripeSubscriptionId="sub_order",
        subscriptionStatus="active",
    )

    cancelled = build_event(
        "customer.subscription.deleted",
        subscription(subscription_id="sub_order", customer="cus_order", status="canceled"),
        created=1679609900,
    )
    assert _send(wired, cancelled)["statusCode"] == 200
    assert wired._user_repo.get_user("u_order")["tier"] == "free"

    # Generated two minutes BEFORE the cancellation, delivered after it.
    stale = build_event(
        "customer.subscription.updated",
        subscription(subscription_id="sub_order", customer="cus_order", status="active"),
        created=1679609780,
    )
    assert _send(wired, stale)["statusCode"] == 200

    item = wired._user_repo.get_user("u_order")
    assert item["tier"] == "free"
    assert item["subscriptionStatus"] == "canceled"


def test_stale_checkout_completion_cannot_resurrect_paid(wired):
    """Same ordering hazard through the checkout handler."""
    _seed_subscriber(wired, "u_order2", "cus_order2", subscriptionStatus="active")

    assert (
        _send(
            wired,
            build_event(
                "customer.subscription.deleted",
                subscription(
                    subscription_id="sub_order2", customer="cus_order2", status="canceled"
                ),
                created=1679609900,
            ),
        )["statusCode"]
        == 200
    )
    assert wired._user_repo.get_user("u_order2")["tier"] == "free"

    assert (
        _send(
            wired,
            build_event(
                "checkout.session.completed",
                checkout_session(user_id="u_order2", customer="cus_order2"),
                created=1679609780,
            ),
        )["statusCode"]
        == 200
    )
    assert wired._user_repo.get_user("u_order2")["tier"] == "free"


def test_stale_event_does_not_move_revenue_counters(wired):
    """A rejected transition must not book revenue either.

    Applying the counter while refusing the tier write would leave
    activeSubscribers permanently above the number of actual subscribers.
    """
    _seed_subscriber(wired, "u_rev", "cus_rev", subscriptionStatus="active")
    wired._user_repo.increment_revenue_counter("activeSubscribers", 1)

    _send(
        wired,
        build_event(
            "customer.subscription.deleted",
            subscription(subscription_id="sub_rev", customer="cus_rev", status="canceled"),
            created=1679609900,
        ),
    )
    assert wired._user_repo.get_revenue().get("activeSubscribers", 0) == 0

    _send(
        wired,
        build_event(
            "checkout.session.completed",
            checkout_session(user_id="u_rev", customer="cus_rev"),
            created=1679609780,
        ),
    )
    revenue = wired._user_repo.get_revenue()
    assert revenue.get("activeSubscribers", 0) == 0
    assert revenue.get("monthlyChurn", 0) == 1


def test_stale_event_sends_no_lifecycle_email(wired, monkeypatch):
    """A transition that did not happen must not be announced to the user."""
    from notifications import sender as email_sender

    _seed_subscriber(wired, "u_mail", "cus_mail", email="m@x.com", subscriptionStatus="active")
    _send(
        wired,
        build_event(
            "customer.subscription.deleted",
            subscription(subscription_id="sub_mail", customer="cus_mail", status="canceled"),
            created=1679609900,
        ),
    )

    sent: list[str] = []
    monkeypatch.setattr(email_sender, "send_email", lambda to, subj, html, text: sent.append(subj))
    _send(
        wired,
        build_event(
            "customer.subscription.updated",
            subscription(subscription_id="sub_mail", customer="cus_mail", status="active"),
            created=1679609780,
        ),
    )
    assert sent == []


def test_in_order_events_still_apply(wired):
    """The guard must reject only what is genuinely older.

    Every transition below is newer than the one before it, which is the
    ordinary case and must be unaffected.
    """
    _seed_subscriber(wired, "u_seq", "cus_seq", tier="free", subscriptionStatus="")

    _send(
        wired,
        build_event(
            "checkout.session.completed",
            checkout_session(user_id="u_seq", customer="cus_seq", subscription="sub_seq"),
            created=1679609700,
        ),
    )
    assert wired._user_repo.get_user("u_seq")["tier"] == "paid"

    _send(
        wired,
        build_event(
            "invoice.payment_failed",
            invoice(customer="cus_seq", subscription_id="sub_seq"),
            created=1679609800,
        ),
    )
    item = wired._user_repo.get_user("u_seq")
    assert item["tier"] == "paid"
    assert item["subscriptionStatus"] == "past_due"

    _send(
        wired,
        build_event(
            "customer.subscription.deleted",
            subscription(subscription_id="sub_seq", customer="cus_seq", status="canceled"),
            created=1679609900,
        ),
    )
    assert wired._user_repo.get_user("u_seq")["tier"] == "free"


def test_same_second_events_both_apply(wired):
    """Equal timestamps are not stale.

    Stripe stamps ``created`` to the second, and a cancellation commonly emits
    ``customer.subscription.updated`` and ``.deleted`` in the same one.
    Rejecting equality would drop the second of every such pair.
    """
    _seed_subscriber(wired, "u_same", "cus_same", subscriptionStatus="active")

    _send(
        wired,
        build_event(
            "customer.subscription.updated",
            subscription(subscription_id="sub_same", customer="cus_same", status="canceled"),
            created=1679609900,
        ),
    )
    _send(
        wired,
        build_event(
            "customer.subscription.deleted",
            subscription(subscription_id="sub_same", customer="cus_same", status="canceled"),
            created=1679609900,
        ),
    )
    item = wired._user_repo.get_user("u_same")
    assert item["tier"] == "free"
    assert item["subscriptionStatus"] == "canceled"
    assert wired._user_repo.get_revenue().get("monthlyChurn", 0) == 1


# ---- Checkout completion is not the same as payment ----
#
# checkout.session.completed fires when the session finishes, which is not
# the same as the customer having paid. A delayed payment method (ACH debit,
# bank transfer, some wallets) completes the session with
# payment_status="unpaid" and settles minutes-to-days later, or never.
# Granting paid access on completion alone hands out the product before —
# and, on failure, without — payment.


def test_unpaid_checkout_does_not_grant_paid(wired):
    """The finding: a signed, complete session that has not been paid for."""
    wired._user_repo.get_or_create_user("u_unpaid")
    r = _send(
        wired,
        build_event(
            "checkout.session.completed",
            checkout_session(
                user_id="u_unpaid", customer="cus_unpaid", payment_status="unpaid"
            ),
        ),
    )
    assert r["statusCode"] == 200
    assert wired._user_repo.get_user("u_unpaid").get("tier", "free") == "free"


def test_unpaid_checkout_books_no_revenue_and_no_welcome(wired, monkeypatch):
    """A grant that did not happen must not be counted or announced."""
    from notifications import sender as email_sender

    wired._user_repo.get_or_create_user("u_unpaid2", email="u@x.com")
    sent: list[str] = []
    monkeypatch.setattr(email_sender, "send_email", lambda to, s, h, t: sent.append(s))

    _send(
        wired,
        build_event(
            "checkout.session.completed",
            checkout_session(
                user_id="u_unpaid2", customer="cus_unpaid2", payment_status="unpaid"
            ),
        ),
    )
    assert wired._user_repo.get_revenue().get("activeSubscribers", 0) == 0
    assert sent == []


def test_incomplete_checkout_session_does_not_grant_paid(wired):
    """``status`` is the session's own lifecycle; only "complete" qualifies."""
    wired._user_repo.get_or_create_user("u_open")
    _send(
        wired,
        build_event(
            "checkout.session.completed",
            checkout_session(user_id="u_open", customer="cus_open", status="open"),
        ),
    )
    assert wired._user_repo.get_user("u_open").get("tier", "free") == "free"


def test_non_subscription_checkout_does_not_grant_paid(wired):
    """/billing/checkout only ever creates subscription-mode sessions.

    A one-off payment-mode session reaching this handler is not the thing the
    paid tier is sold as, and granting on it would price a subscription at
    one payment.
    """
    wired._user_repo.get_or_create_user("u_mode")
    _send(
        wired,
        build_event(
            "checkout.session.completed",
            checkout_session(user_id="u_mode", customer="cus_mode", mode="payment"),
        ),
    )
    assert wired._user_repo.get_user("u_mode").get("tier", "free") == "free"


def test_no_payment_required_checkout_grants_paid(wired):
    """A full-coupon or trial checkout is legitimately paid-equivalent.

    Stripe reports ``no_payment_required`` rather than ``paid`` for these, so
    a naive ``payment_status == "paid"`` check would refuse real customers.
    """
    wired._user_repo.get_or_create_user("u_free_sub")
    _send(
        wired,
        build_event(
            "checkout.session.completed",
            checkout_session(
                user_id="u_free_sub",
                customer="cus_free_sub",
                payment_status="no_payment_required",
            ),
        ),
    )
    assert wired._user_repo.get_user("u_free_sub")["tier"] == "paid"


def test_delayed_payment_grants_paid_on_async_success(wired):
    """The settlement event is what grants a delayed-method checkout.

    Refusing the unpaid completion above is only correct if the customer
    still gets what they bought once the payment clears.
    """
    wired._user_repo.get_or_create_user("u_async")
    session = checkout_session(
        user_id="u_async", customer="cus_async", subscription="sub_async"
    )

    unpaid = dict(session, payment_status="unpaid")
    _send(wired, build_event("checkout.session.completed", unpaid, created=1679609700))
    assert wired._user_repo.get_user("u_async").get("tier", "free") == "free"

    _send(
        wired,
        build_event(
            "checkout.session.async_payment_succeeded", session, created=1679609800
        ),
    )
    item = wired._user_repo.get_user("u_async")
    assert item["tier"] == "paid"
    assert item["subscriptionStatus"] == "active"
    assert item["stripeSubscriptionId"] == "sub_async"


def test_async_payment_failure_leaves_the_user_free(wired):
    """A failed settlement must not be a second chance at the grant."""
    wired._user_repo.get_or_create_user("u_async_fail")
    _send(
        wired,
        build_event(
            "checkout.session.async_payment_failed",
            checkout_session(
                user_id="u_async_fail", customer="cus_async_fail", payment_status="unpaid"
            ),
        ),
    )
    assert wired._user_repo.get_user("u_async_fail").get("tier", "free") == "free"
