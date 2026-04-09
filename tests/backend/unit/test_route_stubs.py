"""Tests for Phase 1 route stubs that return 501 Not Implemented."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from lambda_function import lambda_handler


def _event(method: str, path: str) -> dict:
    return {
        "rawPath": path,
        "requestContext": {"http": {"method": method, "sourceIp": "127.0.0.1"}},
        "headers": {},
        "body": "",
    }


@patch("config.auth_enabled", False)
def test_me_stub_returns_501():
    resp = lambda_handler(_event("GET", "/me"), None)
    assert resp["statusCode"] == 501
    body = json.loads(resp["body"])
    assert body["error"] == "GET /me not implemented"


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/billing/checkout"),
        ("POST", "/billing/portal"),
        ("POST", "/stripe/webhook"),
    ],
)
@patch("config.billing_enabled", False)
def test_billing_routes_return_501_when_disabled(method, path):
    resp = lambda_handler(_event(method, path), None)
    assert resp["statusCode"] == 501
    body = json.loads(resp["body"])
    assert "billing" in body.get("error", "").lower() or "disabled" in body.get("error", "").lower()
