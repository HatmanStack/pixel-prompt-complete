"""Tests for POST /stripe/webhook."""

from __future__ import annotations

import base64
import importlib
import json
import os

import boto3
import pytest
from moto import mock_aws

from .fixtures.stripe_events import build_event, sign_payload

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
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
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
                AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
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
        lambda_function._user_repo = UserRepository(
            TABLE_NAME, dynamodb_resource=ddb
        )
        yield lambda_function


def _event(body: str, sig: str | None = None, b64: bool = False) -> dict:
    headers = {}
    if sig is not None:
        headers["Stripe-Signature"] = sig
    if b64:
        body_field = base64.b64encode(body.encode()).decode()
    else:
        body_field = body
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


def test_flags_off_returns_501(monkeypatch):
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
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
    payload = build_event("checkout.session.completed", {"client_reference_id": "u1"})
    r = _send(wired, payload, sign=False)
    assert r["statusCode"] == 400


def test_checkout_session_completed_sets_paid(wired):
    wired._user_repo.get_or_create_user("u1", email="u@x.com")
    obj = {
        "client_reference_id": "u1",
        "customer": "cus_1",
        "subscription": "sub_1",
    }
    payload = build_event("checkout.session.completed", obj)
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    item = wired._user_repo.get_user("u1")
    assert item["tier"] == "paid"
    assert item["stripeCustomerId"] == "cus_1"
    assert item["stripeSubscriptionId"] == "sub_1"
    assert item["subscriptionStatus"] == "active"


def test_subscription_updated_syncs_status(wired):
    wired._user_repo.get_or_create_user("u2")
    wired._user_repo.set_tier("u2", "paid", stripeCustomerId="cus_2")
    obj = {
        "id": "sub_2",
        "status": "active",
        "customer": "cus_2",
        "metadata": {"userId": "u2"},
    }
    payload = build_event("customer.subscription.updated", obj)
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    item = wired._user_repo.get_user("u2")
    assert item["tier"] == "paid"
    assert item["subscriptionStatus"] == "active"
    assert item["stripeSubscriptionId"] == "sub_2"


def test_subscription_deleted_downgrades_to_free(wired):
    wired._user_repo.get_or_create_user("u3")
    wired._user_repo.set_tier(
        "u3",
        "paid",
        stripeCustomerId="cus_3",
        stripeSubscriptionId="sub_3",
        subscriptionStatus="active",
    )
    obj = {
        "id": "sub_3",
        "customer": "cus_3",
        "metadata": {"userId": "u3"},
    }
    payload = build_event("customer.subscription.deleted", obj)
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    item = wired._user_repo.get_user("u3")
    assert item["tier"] == "free"
    assert item["subscriptionStatus"] == "canceled"


def test_invoice_payment_failed_marks_past_due_but_keeps_paid(wired):
    wired._user_repo.get_or_create_user("u4")
    wired._user_repo.set_tier("u4", "paid", stripeCustomerId="cus_4")
    obj = {"customer": "cus_4", "metadata": {"userId": "u4"}}
    payload = build_event("invoice.payment_failed", obj)
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    item = wired._user_repo.get_user("u4")
    assert item["tier"] == "paid"
    assert item["subscriptionStatus"] == "past_due"


def test_unknown_event_type_returns_200_noop(wired):
    payload = build_event("customer.updated", {"id": "cus_x"})
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    assert _body(r)["received"] is True


def test_duplicate_event_is_idempotent(wired):
    wired._user_repo.get_or_create_user("u5")
    obj = {
        "client_reference_id": "u5",
        "customer": "cus_5",
        "subscription": "sub_5",
    }
    payload = build_event("checkout.session.completed", obj, event_id="evt_dup")
    r1 = _send(wired, payload)
    r2 = _send(wired, payload)
    assert r1["statusCode"] == 200
    assert r2["statusCode"] == 200
    item = wired._user_repo.get_user("u5")
    assert item["tier"] == "paid"
    assert item["stripeCustomerId"] == "cus_5"


def test_event_without_user_id_is_noop(wired):
    payload = build_event("checkout.session.completed", {"customer": "cus_x"})
    r = _send(wired, payload)
    assert r["statusCode"] == 200


def test_handler_exception_returns_500(wired, monkeypatch):
    payload = build_event(
        "checkout.session.completed",
        {"client_reference_id": "u7", "customer": "cus_7"},
    )
    from billing import webhook as wh

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setitem(wh._DISPATCH, "checkout.session.completed", boom)
    r = _send(wired, payload)
    assert r["statusCode"] == 500


def test_invalid_payload_returns_400(wired):
    import stripe as real_stripe

    from billing import webhook as wh

    def raise_value(*a, **k):
        raise ValueError("not json")

    wh_module = wh.stripe.Webhook
    orig = wh_module.construct_event
    wh.stripe.Webhook.construct_event = raise_value
    try:
        r = wired.lambda_handler(
            _event("{}", sig=sign_payload("{}", WEBHOOK_SECRET)), None
        )
    finally:
        wh.stripe.Webhook.construct_event = orig
    assert r["statusCode"] == 400
    _ = real_stripe  # keep import happy


def test_subscription_canceled_status_downgrades(wired):
    wired._user_repo.get_or_create_user("u8")
    obj = {
        "id": "sub_8",
        "status": "canceled",
        "customer": "cus_8",
        "metadata": {"userId": "u8"},
    }
    payload = build_event("customer.subscription.updated", obj)
    r = _send(wired, payload)
    assert r["statusCode"] == 200
    item = wired._user_repo.get_user("u8")
    assert item["tier"] == "free"


def test_stripe_not_configured_returns_500(wired, monkeypatch):
    from billing import stripe_client
    import config as cfg

    monkeypatch.setattr(cfg, "stripe_secret_key", "")
    stripe_client.reset_stripe_client()
    payload = build_event("checkout.session.completed", {"client_reference_id": "u"})
    r = _send(wired, payload)
    assert r["statusCode"] == 500


def test_base64_body_verified_correctly(wired):
    wired._user_repo.get_or_create_user("u6")
    obj = {"client_reference_id": "u6", "customer": "cus_6", "subscription": "sub_6"}
    payload = build_event("checkout.session.completed", obj)
    r = _send(wired, payload, b64=True)
    assert r["statusCode"] == 200
    item = wired._user_repo.get_user("u6")
    assert item["tier"] == "paid"
