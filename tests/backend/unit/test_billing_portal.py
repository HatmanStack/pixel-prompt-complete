"""Tests for POST /billing/portal."""

from __future__ import annotations

import importlib
import json
import os
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


TABLE_NAME = "pixel-prompt-users-portal"


@pytest.fixture
def billing_on(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("BILLING_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "secret")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_dummy")
    monkeypatch.setenv("STRIPE_PORTAL_RETURN_URL", "https://example.com/return")
    monkeypatch.setenv("USERS_TABLE_NAME", TABLE_NAME)
    import config
    importlib.reload(config)
    from billing import stripe_client
    stripe_client.reset_stripe_client()
    yield
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
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


def _event(claims=None):
    e = {
        "rawPath": "/billing/portal",
        "requestContext": {"http": {"method": "POST", "sourceIp": "1.2.3.4"}},
        "headers": {},
        "body": "{}",
    }
    if claims:
        e["requestContext"]["authorizer"] = {"jwt": {"claims": claims}}
    return e


def _body(r):
    return json.loads(r["body"])


def test_flags_off_returns_501(monkeypatch):
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    import config
    importlib.reload(config)
    import lambda_function
    importlib.reload(lambda_function)
    r = lambda_function.lambda_handler(_event(claims={"sub": "u1"}), None)
    assert r["statusCode"] == 501


def test_unauthenticated_returns_401(wired):
    r = wired.lambda_handler(_event(), None)
    assert r["statusCode"] == 401


def test_no_customer_returns_409(wired):
    r = wired.lambda_handler(_event(claims={"sub": "u1"}), None)
    assert r["statusCode"] == 409
    assert _body(r)["error"] == "no_subscription"


def test_happy_path_returns_url(wired):
    wired._user_repo.get_or_create_user("u2")
    wired._user_repo.set_stripe_customer_id("u2", "cus_abc")
    fake = MagicMock()
    fake.billing_portal.Session.create.return_value = {"url": "https://stripe/portal"}
    fake.error = __import__("stripe").error
    with patch("billing.portal.get_stripe", return_value=fake):
        r = wired.lambda_handler(_event(claims={"sub": "u2"}), None)
    assert r["statusCode"] == 200
    assert _body(r)["url"] == "https://stripe/portal"
    kwargs = fake.billing_portal.Session.create.call_args.kwargs
    assert kwargs["customer"] == "cus_abc"
    assert kwargs["return_url"] == "https://example.com/return"


def test_unexpected_exception_returns_500(wired):
    wired._user_repo.get_or_create_user("u4")
    wired._user_repo.set_stripe_customer_id("u4", "cus_y")
    fake = MagicMock()
    fake.error = __import__("stripe").error
    fake.billing_portal.Session.create.side_effect = RuntimeError("oops")
    with patch("billing.portal.get_stripe", return_value=fake):
        r = wired.lambda_handler(_event(claims={"sub": "u4"}), None)
    assert r["statusCode"] == 500


def test_stripe_error_returns_502(wired):
    import stripe as real_stripe

    wired._user_repo.get_or_create_user("u3")
    wired._user_repo.set_stripe_customer_id("u3", "cus_x")
    fake = MagicMock()
    fake.error = real_stripe.error
    fake.billing_portal.Session.create.side_effect = real_stripe.error.StripeError("x")
    with patch("billing.portal.get_stripe", return_value=fake):
        r = wired.lambda_handler(_event(claims={"sub": "u3"}), None)
    assert r["statusCode"] == 502
