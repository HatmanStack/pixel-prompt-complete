"""Tests for auth.guest_token."""

import pytest

from auth.guest_token import GuestTokenService


def test_issue_and_verify_round_trip():
    svc = GuestTokenService("s3cret")
    token = svc.issue()
    token_id = svc.verify(token)
    assert token_id is not None
    assert isinstance(token_id, str)


def test_tampered_token_rejected():
    svc = GuestTokenService("s3cret")
    token = svc.issue()
    tid, sig = token.split(".")
    bad = f"{tid}.{sig[:-2]}AA"
    assert svc.verify(bad) is None
    assert svc.verify("garbage") is None
    assert svc.verify("no-dot") is None
    assert svc.verify("") is None


def test_empty_secret_rejected_at_init():
    with pytest.raises(ValueError):
        GuestTokenService("")


def test_token_id_is_random():
    svc = GuestTokenService("x")
    assert svc.issue() != svc.issue()


def test_different_secret_rejects_token():
    a = GuestTokenService("a")
    b = GuestTokenService("b")
    assert b.verify(a.issue()) is None


def test_parse_cookie_header_multiple_cookies():
    h = "foo=bar; pp_guest=abc.def; baz=qux"
    assert GuestTokenService.extract_from_cookie_header(h) == "abc.def"
    assert GuestTokenService.extract_from_cookie_header("other=1") is None
    assert GuestTokenService.extract_from_cookie_header(None) is None
    assert GuestTokenService.extract_from_cookie_header("") is None


def test_set_cookie_header_format():
    out = GuestTokenService.set_cookie_header("abc.def", 3600)
    assert "pp_guest=abc.def" in out
    assert "HttpOnly" in out
    assert "Secure" in out
    assert "SameSite=Lax" in out
    assert "Max-Age=3600" in out
    assert "Path=/" in out


# ---- Identity canonicalization ----
#
# A guest quota is keyed on the string verify() returns. Returning the
# caller's spelling rather than one derived from the authenticated bytes
# meant one signed token had many spellings, each with its own counter.


def _alternate_spellings(token_id_b64: str) -> list[str]:
    """Every base64url spelling of the same 16 bytes.

    A 16-byte id occupies 22 unpadded base64url characters, whose last
    character carries 4 bits that encode nothing. Python's decoder ignores
    those bits rather than rejecting them, so 16 distinct strings decode to
    one identical token id — and every one of them passes an HMAC computed
    over the decoded bytes.
    """
    import base64

    raw = base64.urlsafe_b64decode(token_id_b64 + "==")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    out = []
    for ch in alphabet:
        candidate = token_id_b64[:-1] + ch
        try:
            if base64.urlsafe_b64decode(candidate + "==") == raw:
                out.append(candidate)
        except Exception:
            continue
    return out


def test_noncanonical_spellings_exist_and_all_verify():
    """Guard on the premise: these really are accepted, not hypothetical."""
    svc = GuestTokenService("s3cret")
    token = svc.issue()
    token_id_b64, sig = token.split(".")

    spellings = _alternate_spellings(token_id_b64)
    assert len(spellings) > 1
    for spelling in spellings:
        assert svc.verify(f"{spelling}.{sig}") is not None


def test_all_spellings_resolve_to_one_identity():
    """The finding: one token must not yield many quota identities."""
    svc = GuestTokenService("s3cret")
    token = svc.issue()
    token_id_b64, sig = token.split(".")

    identities = {svc.verify(f"{s}.{sig}") for s in _alternate_spellings(token_id_b64)}
    assert len(identities) == 1


def test_verify_returns_the_canonical_encoding():
    """The identity is derived from the authenticated bytes, not the input."""
    import base64

    svc = GuestTokenService("s3cret")
    token = svc.issue()
    token_id_b64, sig = token.split(".")
    returned = svc.verify(token)

    assert returned == token_id_b64
    raw = base64.urlsafe_b64decode(token_id_b64 + "==")
    assert returned == base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    assert "=" not in returned


def test_padded_spelling_resolves_to_the_same_identity():
    """A cookie that arrives with its padding intact is the same guest."""
    svc = GuestTokenService("s3cret")
    token = svc.issue()
    token_id_b64, sig = token.split(".")
    assert svc.verify(f"{token_id_b64}==.{sig}") == svc.verify(token)
