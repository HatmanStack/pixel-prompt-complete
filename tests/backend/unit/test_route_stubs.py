"""Tests for Phase 1 route stubs that return 501 Not Implemented."""

from __future__ import annotations

import json

import pytest

from lambda_function import lambda_handler


def _event(method: str, path: str) -> dict:
    return {
        "rawPath": path,
        "requestContext": {"http": {"method": method, "sourceIp": "127.0.0.1"}},
        "headers": {},
        "body": "",
    }


@pytest.mark.parametrize(
    "method,path,endpoint",
    [
        ("GET", "/me", "GET /me"),
        ("POST", "/billing/checkout", "POST /billing/checkout"),
        ("POST", "/billing/portal", "POST /billing/portal"),
        ("POST", "/stripe/webhook", "POST /stripe/webhook"),
    ],
)
def test_route_stub_returns_501(method, path, endpoint):
    resp = lambda_handler(_event(method, path), None)
    assert resp["statusCode"] == 501
    body = json.loads(resp["body"])
    assert body["error"] == f"{endpoint} not implemented"
