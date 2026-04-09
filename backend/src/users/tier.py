"""Tier resolution from API Gateway events.

Reads the Lambda event, decides whether the caller is guest / free / paid
and returns a :class:`TierContext`. Never re-verifies JWT signatures; the
HttpApi JWT authorizer is responsible for that.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Literal

import config
from auth.guest_token import GuestTokenService
from users.repository import UserRepository


@dataclass(frozen=True)
class TierContext:
    tier: Literal["guest", "free", "paid"]
    user_id: str
    email: str | None
    is_authenticated: bool
    guest_token_id: str | None
    issue_guest_cookie: bool
    new_guest_token: str | None = None


def extract_claims(event: dict[str, Any]) -> dict[str, Any] | None:
    rc = event.get("requestContext") or {}
    auth = rc.get("authorizer") or {}
    jwt = auth.get("jwt") or {}
    claims = jwt.get("claims")
    if claims and isinstance(claims, dict) and claims.get("sub"):
        return claims
    return None


def _cookie_header(event: dict[str, Any]) -> str | None:
    headers = event.get("headers") or {}
    # headers may be any-case
    for k, v in headers.items():
        if k.lower() == "cookie":
            return v
    return None


def _source_ip(event: dict[str, Any]) -> str:
    return (event.get("requestContext") or {}).get("http", {}).get("sourceIp") or "unknown"


def resolve_tier(
    event: dict[str, Any],
    repo: UserRepository,
    guest_service: GuestTokenService,
) -> TierContext:
    """Return the :class:`TierContext` for the given request."""
    if not config.auth_enabled:
        return TierContext(
            tier="paid",
            user_id="anon",
            email=None,
            is_authenticated=False,
            guest_token_id=None,
            issue_guest_cookie=False,
        )

    claims = extract_claims(event)
    if claims:
        sub = claims["sub"]
        email = claims.get("email")
        user = repo.get_or_create_user(sub, email=email)
        tier = user.get("tier", "free")
        if tier not in ("free", "paid"):
            tier = "free"
        return TierContext(
            tier=tier,
            user_id=sub,
            email=email,
            is_authenticated=True,
            guest_token_id=None,
            issue_guest_cookie=False,
        )

    # Guest path.
    cookie_header = _cookie_header(event)
    existing = guest_service.extract_from_cookie_header(cookie_header)
    token_id = guest_service.verify(existing) if existing else None
    if token_id is not None:
        return TierContext(
            tier="guest",
            user_id=f"guest#{token_id}",
            email=None,
            is_authenticated=False,
            guest_token_id=token_id,
            issue_guest_cookie=False,
        )

    new_token = guest_service.issue()
    new_token_id = guest_service.verify(new_token)
    if new_token_id is None:
        raise ValueError(
            "Failed to verify newly issued guest token. "
            "GUEST_TOKEN_SECRET may have changed between issue and verify."
        )
    ip_hash = hashlib.sha256(_source_ip(event).encode()).hexdigest()[:16]
    now = int(time.time())
    repo.upsert_guest(new_token_id, ip_hash, now + config.guest_window_seconds + 300)
    return TierContext(
        tier="guest",
        user_id=f"guest#{new_token_id}",
        email=None,
        is_authenticated=False,
        guest_token_id=new_token_id,
        issue_guest_cookie=True,
        new_guest_token=new_token,
    )
