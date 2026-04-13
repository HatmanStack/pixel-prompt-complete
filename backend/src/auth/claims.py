"""Admin authorization helpers for Cognito group-based access control.

Extracts ``cognito:groups`` from the JWT claims passed through API Gateway's
HttpApi JWT authorizer.  The authorizer serializes JSON array claims into
their string form (e.g. ``"[admins, editors]"``), so both string and native
list formats are handled defensively.
"""

from __future__ import annotations

from typing import Any

from users.tier import extract_claims


def extract_admin_groups(event: dict[str, Any]) -> list[str]:
    """Extract the ``cognito:groups`` claim from the JWT in the event.

    Handles both string format (``"[admins, editors]"``) from API Gateway
    HttpApi and native list format (``["admins", "editors"]``).

    Returns an empty list when no groups claim is present.
    """
    claims = extract_claims(event)
    if not claims:
        return []

    groups = claims.get("cognito:groups")
    if groups is None:
        return []

    if isinstance(groups, list):
        return groups

    if isinstance(groups, str):
        if not groups:
            return []
        # Strip brackets and split on comma
        stripped = groups.strip("[] ")
        if not stripped:
            return []
        return [g.strip() for g in stripped.split(",")]

    return []


def is_admin(event: dict[str, Any]) -> bool:
    """Return ``True`` if the caller belongs to the ``admins`` Cognito group."""
    return "admins" in extract_admin_groups(event)
