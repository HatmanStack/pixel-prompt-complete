"""Tests for admin auth middleware.

Covers:
- extract_admin_groups with list and string formats
- is_admin with admin and non-admin users
- require_admin_request with admin_enabled, auth, and group validation
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _make_event(groups=None, has_claims=True):
    """Build a minimal API Gateway event with optional cognito:groups."""
    claims = {"sub": "user-123", "email": "admin@example.com"}
    if groups is not None:
        claims["cognito:groups"] = groups
    if not has_claims:
        return {"requestContext": {}}
    return {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": claims,
                }
            }
        }
    }


class TestExtractAdminGroups:
    def test_list_format(self):
        from auth.claims import extract_admin_groups

        event = _make_event(groups=["admins"])
        assert extract_admin_groups(event) == ["admins"]

    def test_string_format_single(self):
        from auth.claims import extract_admin_groups

        event = _make_event(groups="[admins]")
        assert extract_admin_groups(event) == ["admins"]

    def test_string_format_multiple(self):
        from auth.claims import extract_admin_groups

        event = _make_event(groups="[admins, editors]")
        result = extract_admin_groups(event)
        assert "admins" in result
        assert "editors" in result

    def test_no_groups_claim(self):
        from auth.claims import extract_admin_groups

        event = _make_event(groups=None)
        assert extract_admin_groups(event) == []

    def test_no_claims_at_all(self):
        from auth.claims import extract_admin_groups

        event = _make_event(has_claims=False)
        assert extract_admin_groups(event) == []

    def test_empty_string(self):
        from auth.claims import extract_admin_groups

        event = _make_event(groups="")
        assert extract_admin_groups(event) == []

    def test_empty_list(self):
        from auth.claims import extract_admin_groups

        event = _make_event(groups=[])
        assert extract_admin_groups(event) == []


class TestIsAdmin:
    def test_returns_true_for_admin(self):
        from auth.claims import is_admin

        event = _make_event(groups=["admins"])
        assert is_admin(event) is True

    def test_returns_true_for_admin_string(self):
        from auth.claims import is_admin

        event = _make_event(groups="[admins]")
        assert is_admin(event) is True

    def test_returns_false_for_non_admin(self):
        from auth.claims import is_admin

        event = _make_event(groups=["editors"])
        assert is_admin(event) is False

    def test_returns_false_for_no_groups(self):
        from auth.claims import is_admin

        event = _make_event(groups=None)
        assert is_admin(event) is False


class TestRequireAdminRequest:
    @patch("config.admin_enabled", False)
    @patch("config.auth_enabled", True)
    def test_returns_501_when_admin_disabled(self):
        from admin.auth import require_admin_request

        event = _make_event(groups=["admins"])
        claims, err = require_admin_request(event)
        assert claims is None
        assert err is not None
        assert err["statusCode"] == 501

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", False)
    def test_returns_501_when_auth_disabled(self):
        from admin.auth import require_admin_request

        event = _make_event(groups=["admins"])
        claims, err = require_admin_request(event)
        assert claims is None
        assert err is not None
        assert err["statusCode"] == 501

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_returns_401_when_no_jwt(self):
        from admin.auth import require_admin_request

        event = _make_event(has_claims=False)
        claims, err = require_admin_request(event)
        assert claims is None
        assert err is not None
        assert err["statusCode"] == 401

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_returns_403_when_not_admin(self):
        from admin.auth import require_admin_request

        event = _make_event(groups=["editors"])
        claims, err = require_admin_request(event)
        assert claims is None
        assert err is not None
        assert err["statusCode"] == 403

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_returns_claims_when_admin(self):
        from admin.auth import require_admin_request

        event = _make_event(groups=["admins"])
        claims, err = require_admin_request(event)
        assert err is None
        assert claims is not None
        assert claims["sub"] == "user-123"
