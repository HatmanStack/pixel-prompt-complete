"""Tests for the /me endpoint."""

from __future__ import annotations

import importlib
import json
import os

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


@pytest.fixture
def flags_on(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "secret")
    import config
    importlib.reload(config)
    import auth.guest_token as gt
    gt.reset_guest_token_service()
    yield
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.delenv("GUEST_TOKEN_SECRET", raising=False)
    importlib.reload(config)
    gt.reset_guest_token_service()


@pytest.fixture
def wired(flags_on):
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="pixel-prompt-users",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        import lambda_function
        importlib.reload(lambda_function)
        from users.repository import UserRepository
        lambda_function._user_repo = UserRepository(
            "pixel-prompt-users", dynamodb_resource=ddb
        )
        yield lambda_function


def _event(claims=None):
    e = {
        "rawPath": "/me",
        "requestContext": {"http": {"method": "GET", "sourceIp": "1.2.3.4"}},
        "headers": {},
    }
    if claims:
        e["requestContext"]["authorizer"] = {"jwt": {"claims": claims}}
    return e


def _body(r):
    return json.loads(r["body"])


def test_me_unauthenticated_returns_401(wired):
    r = wired.lambda_handler(_event(), None)
    assert r["statusCode"] == 401
    assert _body(r)["error"] == "AUTH_REQUIRED"


def test_me_free_tier(wired):
    r = wired.lambda_handler(_event(claims={"sub": "u1", "email": "u@x.com"}), None)
    assert r["statusCode"] == 200
    body = _body(r)
    assert body["tier"] == "free"
    assert body["email"] == "u@x.com"
    assert "generate" in body["quota"]
    assert "refine" in body["quota"]
    assert body["quota"]["generate"]["limit"] >= 1


def test_me_paid_tier(wired):
    wired._user_repo.get_or_create_user("u2")
    wired._user_repo.set_tier("u2", "paid", stripeCustomerId="cus_1", subscriptionStatus="active")
    r = wired.lambda_handler(_event(claims={"sub": "u2"}), None)
    assert r["statusCode"] == 200
    body = _body(r)
    assert body["tier"] == "paid"
    assert "refine" in body["quota"]
    assert "generate" not in body["quota"]
    assert body["billing"]["portalAvailable"] is True
    assert body["billing"]["subscriptionStatus"] == "active"


def test_me_flags_off_returns_501(monkeypatch):
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    import config
    importlib.reload(config)
    import lambda_function
    importlib.reload(lambda_function)
    r = lambda_function.lambda_handler(_event(), None)
    assert r["statusCode"] == 501
