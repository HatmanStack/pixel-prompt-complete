"""Admin auth middleware.

Validates that the caller has ``ADMIN_ENABLED`` feature flag on, is
authenticated, and belongs to the ``admins`` Cognito group.
"""

from __future__ import annotations

import json
from typing import Any

import config
from auth.claims import is_admin
from users.tier import extract_claims
from utils.error_responses import admin_disabled, admin_required, auth_required


def require_admin_request(event: dict[str, Any]) -> tuple[dict | None, dict | None]:
    """Validate admin access for a request.

    Returns:
        ``(claims, None)`` on success, or ``(None, error_response)`` on failure.
        The error response is a fully formed API Gateway response dict.
    """
    if not config.admin_enabled:
        return None, _response(501, admin_disabled())

    if not config.auth_enabled:
        return None, _response(501, admin_disabled())

    claims = extract_claims(event)
    if not claims:
        return None, _response(401, auth_required())

    if not is_admin(event):
        return None, _response(403, admin_required())

    return claims, None


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal API Gateway response."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
