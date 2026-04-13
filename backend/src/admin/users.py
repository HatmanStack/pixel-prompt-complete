"""Admin user management endpoints.

Handles:
- ``GET /admin/users`` - paginated user list with optional filters
- ``GET /admin/users/{userId}`` - single user detail
- ``POST /admin/users/{userId}/suspend`` - suspend a user
- ``POST /admin/users/{userId}/unsuspend`` - unsuspend a user
- ``POST /admin/users/{userId}/notify`` - send email to a user
"""

from __future__ import annotations

import base64
import json
from typing import Any

import config
from admin.auth import require_admin_request
from users.repository import UserRepository


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Build an API Gateway response."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _extract_user_id_from_path(path: str) -> str:
    """Extract userId from paths like /admin/users/{userId}[/action]."""
    parts = path.strip("/").split("/")
    # /admin/users/{userId} -> ["admin", "users", "{userId}"]
    # /admin/users/{userId}/suspend -> ["admin", "users", "{userId}", "suspend"]
    if len(parts) >= 3:
        return parts[2]
    return ""


def handle_admin_users_list(
    event: dict[str, Any],
    repo: UserRepository,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """GET /admin/users - paginated user list with optional filters."""
    claims, err = require_admin_request(event)
    if err:
        return err

    params = event.get("queryStringParameters") or {}
    limit = min(int(params.get("limit", "50")), 100)
    tier_filter = params.get("tier")
    suspended_raw = params.get("suspended")
    suspended_filter = None
    if suspended_raw is not None:
        suspended_filter = suspended_raw.lower() == "true"

    last_key_b64 = params.get("lastKey")
    last_key = None
    if last_key_b64:
        try:
            last_key = json.loads(base64.b64decode(last_key_b64))
        except Exception:
            return _response(400, {"error": "Invalid pagination token"})

    items, next_key = repo.scan_users(
        limit=limit,
        last_key=last_key,
        tier_filter=tier_filter,
        suspended_filter=suspended_filter,
    )

    next_key_b64 = None
    if next_key:
        next_key_b64 = base64.b64encode(json.dumps(next_key).encode()).decode()

    return _response(
        200,
        {
            "users": items,
            "nextKey": next_key_b64,
            "count": len(items),
        },
    )


def handle_admin_user_detail(
    event: dict[str, Any],
    repo: UserRepository,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """GET /admin/users/{userId} - single user detail."""
    claims, err = require_admin_request(event)
    if err:
        return err

    path = event.get("rawPath", "")
    user_id = _extract_user_id_from_path(path)
    if not user_id:
        return _response(400, {"error": "userId is required"})

    user = repo.get_user(user_id)
    if not user:
        return _response(404, {"error": f"User {user_id} not found"})

    return _response(200, user)


def handle_admin_suspend(
    event: dict[str, Any],
    repo: UserRepository,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """POST /admin/users/{userId}/suspend - suspend a user."""
    claims, err = require_admin_request(event)
    if err:
        return err

    path = event.get("rawPath", "")
    user_id = _extract_user_id_from_path(path)
    if not user_id:
        return _response(400, {"error": "userId is required"})

    user = repo.get_user(user_id)
    if not user:
        return _response(404, {"error": f"User {user_id} not found"})

    repo.suspend_user(user_id)

    # Send suspension email if SES is enabled and user has email
    if config.ses_enabled and user.get("email"):
        body = json.loads(event.get("body", "{}") or "{}")
        reason = body.get("reason", "Policy violation")
        from notifications.sender import send_email
        from notifications.templates import suspension_notice_email

        subject, html, text = suspension_notice_email(user["email"], reason)
        send_email(user["email"], subject, html, text)

    return _response(200, {"status": "suspended", "userId": user_id})


def handle_admin_unsuspend(
    event: dict[str, Any],
    repo: UserRepository,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """POST /admin/users/{userId}/unsuspend - unsuspend a user."""
    claims, err = require_admin_request(event)
    if err:
        return err

    path = event.get("rawPath", "")
    user_id = _extract_user_id_from_path(path)
    if not user_id:
        return _response(400, {"error": "userId is required"})

    user = repo.get_user(user_id)
    if not user:
        return _response(404, {"error": f"User {user_id} not found"})

    repo.unsuspend_user(user_id)

    return _response(200, {"status": "active", "userId": user_id})


def handle_admin_notify(
    event: dict[str, Any],
    repo: UserRepository,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """POST /admin/users/{userId}/notify - send email to a user."""
    claims, err = require_admin_request(event)
    if err:
        return err

    path = event.get("rawPath", "")
    user_id = _extract_user_id_from_path(path)
    if not user_id:
        return _response(400, {"error": "userId is required"})

    user = repo.get_user(user_id)
    if not user:
        return _response(404, {"error": f"User {user_id} not found"})

    email = user.get("email")
    if not email:
        return _response(400, {"error": "User has no email address"})

    body = json.loads(event.get("body", "{}") or "{}")
    notify_type = body.get("type")
    message = body.get("message")

    if notify_type not in ("warning", "custom"):
        return _response(400, {"error": "type must be 'warning' or 'custom'"})
    if not message:
        return _response(400, {"error": "message is required"})

    if not config.ses_enabled:
        return _response(200, {"status": "failed", "reason": "SES is disabled"})

    from notifications import templates as email_templates
    from notifications.sender import send_email

    if notify_type == "warning":
        subject, html, text = email_templates.warning_email(email, message)
    else:
        custom_subject = body.get("subject")
        if not custom_subject:
            return _response(400, {"error": "subject is required for custom email"})
        subject, html, text = email_templates.custom_email(email, custom_subject, message)

    ok = send_email(email, subject, html, text)
    if ok:
        return _response(200, {"status": "sent", "userId": user_id})
    return _response(200, {"status": "failed", "reason": "email send failed"})
