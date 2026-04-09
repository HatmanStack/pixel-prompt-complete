"""Tests for tier/auth error response factories."""

from utils import error_responses


def test_auth_required():
    body = error_responses.auth_required()
    assert body["error"] == "auth_required"
    assert "Authentication required" in body["message"]


def test_tier_quota_exceeded():
    body = error_responses.tier_quota_exceeded("free", 1712600000)
    assert body["error"] == "tier_quota_exceeded"
    assert body["tier"] == "free"
    assert body["resetAt"] == 1712600000


def test_subscription_required():
    body = error_responses.subscription_required()
    assert body["error"] == "subscription_required"


def test_guest_global_limit():
    body = error_responses.guest_global_limit()
    assert body["error"] == "guest_global_limit"
    assert "sign in" in body["message"]
