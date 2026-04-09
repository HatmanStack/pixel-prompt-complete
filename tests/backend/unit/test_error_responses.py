"""Tests for tier/auth error response factories."""

from utils import error_responses


def test_auth_required():
    body = error_responses.auth_required()
    assert body["error"] == "AUTH_REQUIRED"
    assert "Authentication required" in body["message"]


def test_tier_quota_exceeded():
    body = error_responses.tier_quota_exceeded("free", 1712600000)
    assert body["error"] == "TIER_QUOTA_EXCEEDED"
    assert body["tier"] == "free"
    assert body["resetAt"] == 1712600000


def test_subscription_required():
    body = error_responses.subscription_required()
    assert body["error"] == "SUBSCRIPTION_REQUIRED"


def test_guest_global_limit():
    body = error_responses.guest_global_limit()
    assert body["error"] == "GUEST_GLOBAL_LIMIT"
    assert "sign in" in body["message"]
