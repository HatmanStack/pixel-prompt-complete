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
