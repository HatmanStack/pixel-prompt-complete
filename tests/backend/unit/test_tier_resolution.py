"""Tests for users.tier.resolve_tier."""

from __future__ import annotations

import importlib

import boto3
import pytest
from moto import mock_aws

from auth.guest_token import GuestTokenService


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "testsecret")
    import config
    importlib.reload(config)
    yield
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.delenv("GUEST_TOKEN_SECRET", raising=False)
    importlib.reload(config)


@pytest.fixture
def repo(env):
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="t",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        from users.repository import UserRepository
        yield UserRepository("t", dynamodb_resource=ddb)


def _event(headers=None, claims=None, ip="1.2.3.4"):
    e = {
        "requestContext": {"http": {"sourceIp": ip}},
        "headers": headers or {},
    }
    if claims:
        e["requestContext"]["authorizer"] = {"jwt": {"claims": claims}}
    return e


def test_flags_off_returns_anon_paid(monkeypatch):
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    import config
    importlib.reload(config)
    from users.tier import resolve_tier
    svc = GuestTokenService("x")
    ctx = resolve_tier(_event(), repo=None, guest_service=svc)
    assert ctx.tier == "paid"
    assert ctx.user_id == "anon"
    assert ctx.is_authenticated is False


def test_jwt_claims_return_free_by_default(repo):
    from users.tier import resolve_tier
    svc = GuestTokenService("testsecret")
    ctx = resolve_tier(
        _event(claims={"sub": "cog-1", "email": "u@x.com"}),
        repo=repo,
        guest_service=svc,
    )
    assert ctx.tier == "free"
    assert ctx.user_id == "cog-1"
    assert ctx.is_authenticated
    assert ctx.email == "u@x.com"


def test_jwt_claims_returning_paid_user(repo):
    from users.tier import resolve_tier
    repo.get_or_create_user("cog-2")
    repo.set_tier("cog-2", "paid")
    svc = GuestTokenService("testsecret")
    ctx = resolve_tier(
        _event(claims={"sub": "cog-2"}), repo=repo, guest_service=svc
    )
    assert ctx.tier == "paid"


def test_no_claims_no_cookie_issues_new_token(repo):
    from users.tier import resolve_tier
    svc = GuestTokenService("testsecret")
    ctx = resolve_tier(_event(), repo=repo, guest_service=svc)
    assert ctx.tier == "guest"
    assert ctx.issue_guest_cookie is True
    assert ctx.new_guest_token is not None
    assert ctx.guest_token_id


def test_no_claims_valid_cookie_returns_guest(repo):
    from users.tier import resolve_tier
    svc = GuestTokenService("testsecret")
    token = svc.issue()
    ctx = resolve_tier(
        _event(headers={"Cookie": f"pp_guest={token}"}),
        repo=repo,
        guest_service=svc,
    )
    assert ctx.tier == "guest"
    assert ctx.issue_guest_cookie is False


def test_no_claims_tampered_cookie_issues_new_token(repo):
    from users.tier import resolve_tier
    svc = GuestTokenService("testsecret")
    ctx = resolve_tier(
        _event(headers={"Cookie": "pp_guest=bad.token"}),
        repo=repo,
        guest_service=svc,
    )
    assert ctx.tier == "guest"
    assert ctx.issue_guest_cookie is True
