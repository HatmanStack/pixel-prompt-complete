"""HMAC-signed guest token service.

Self-contained module, no AWS dependencies. Issues and verifies opaque
guest tokens stored in the ``pp_guest`` HttpOnly cookie.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import os
from hashlib import sha256

_COOKIE_NAME = "pp_guest"


def _b64u_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


class GuestTokenService:
    """HMAC-sign and verify guest tokens."""

    def __init__(self, secret: str) -> None:
        if not secret:
            raise ValueError("GuestTokenService requires a non-empty secret")
        self._secret = secret.encode("utf-8")

    def issue(self) -> str:
        token_id = os.urandom(16)
        sig = hmac.new(self._secret, token_id, sha256).digest()
        return f"{_b64u_encode(token_id)}.{_b64u_encode(sig)}"

    def verify(self, token: str) -> str | None:
        """Return the canonical token id, or None if the token is not ours.

        The return value is the guest's **identity**: quota counters, the
        age-affirmation record and the DynamoDB row are all keyed on it. So
        it is re-encoded from the decoded bytes rather than handed back as
        the caller spelled it.

        A 16-byte token id occupies 22 unpadded base64url characters, and the
        last one carries four bits that encode nothing. Python's decoder
        ignores those bits instead of rejecting them, so sixteen distinct
        strings decode to one identical token id — and every one of them
        passes an HMAC computed over the decoded bytes. Returning the input
        spelling therefore turned one signed token into sixteen quota
        identities, each with its own counter, for a caller who only had to
        edit the last character of their own cookie.

        Deriving the identity from the bytes the signature actually covers
        makes the aliases collapse. Rejecting noncanonical input instead
        would work too, but it would also reject a cookie that arrived with
        its padding intact, which is a legitimate spelling of the same guest.
        """
        if not token or "." not in token:
            return None
        try:
            token_id_b64, sig_b64 = token.split(".", 1)
            token_id = _b64u_decode(token_id_b64)
            sig = _b64u_decode(sig_b64)
        except (ValueError, binascii.Error):
            return None
        expected = hmac.new(self._secret, token_id, sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        return _b64u_encode(token_id)

    @staticmethod
    def extract_from_cookie_header(header: str | None) -> str | None:
        if not header:
            return None
        for part in header.split(";"):
            part = part.strip()
            if part.startswith(f"{_COOKIE_NAME}="):
                return part[len(_COOKIE_NAME) + 1 :]
        return None

    @staticmethod
    def set_cookie_header(token: str, max_age: int) -> str:
        return f"{_COOKIE_NAME}={token}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age={max_age}"


_service: GuestTokenService | None = None


def get_guest_token_service() -> GuestTokenService:
    """Return a lazy singleton using ``config.guest_token_secret``."""
    global _service
    if _service is None:
        import config

        _service = GuestTokenService(config.guest_token_secret)
    return _service


def reset_guest_token_service() -> None:
    """Reset the cached singleton (test helper)."""
    global _service
    _service = None
