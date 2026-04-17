"""Tests for Phase 1 route stubs that return 501 Not Implemented."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


def _event(method: str, path: str) -> dict:
    return {
        "rawPath": path,
        "requestContext": {"http": {"method": method, "sourceIp": "127.0.0.1"}},
        "headers": {},
        "body": "",
    }


def _get_lambda_handler():
    from lambda_function import lambda_handler
    return lambda_handler


@patch("config.auth_enabled", False)
def test_me_stub_returns_501():
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        lambda_handler = _get_lambda_handler()
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        lambda_handler = _get_lambda_handler()
        resp = lambda_handler(_event(method, path), None)
    assert resp["statusCode"] == 501
    body = json.loads(resp["body"])
    assert "billing" in body.get("error", "").lower() or "disabled" in body.get("error", "").lower()
