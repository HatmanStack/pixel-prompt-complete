"""Cloudflare Turnstile CAPTCHA server-side verification.

Verifies tokens by POSTing to the Turnstile ``siteverify`` endpoint.
Uses ``urllib.request`` (stdlib) to avoid adding a dependency.
"""

from __future__ import annotations

import json
import urllib.request

import config
from utils.logger import StructuredLogger

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_TIMEOUT_SECONDS = 5


def verify_turnstile(token: str, remote_ip: str | None = None) -> bool:
    """Verify a Turnstile CAPTCHA token.

    Args:
        token: The CAPTCHA response token from the client.
        remote_ip: Optional client IP to include in verification.

    Returns:
        True if the token is valid, False otherwise (fail closed).
    """
    payload: dict[str, str] = {
        "secret": config.turnstile_secret_key,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _VERIFY_URL,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            result = json.loads(resp.read())
            return bool(result.get("success", False))
    except Exception as e:
        StructuredLogger.warning(f"Turnstile verification error: {e}")
        return False
