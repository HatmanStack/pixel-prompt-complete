"""Tests for ops.captcha Turnstile verification."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock
from urllib.error import URLError

import pytest


def test_verify_turnstile_success():
    from ops.captcha import verify_turnstile

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"success": True}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
        result = verify_turnstile("valid-token")

    assert result is True
    # Verify the request was made correctly
    call_args = mock_open.call_args
    req = call_args[0][0]
    assert req.full_url == "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def test_verify_turnstile_failure():
    from ops.captcha import verify_turnstile

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"success": False}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = verify_turnstile("invalid-token")

    assert result is False


def test_verify_turnstile_network_error():
    from ops.captcha import verify_turnstile

    with patch("urllib.request.urlopen", side_effect=URLError("Connection refused")):
        result = verify_turnstile("any-token")

    # Fail closed on network errors
    assert result is False


def test_verify_turnstile_timeout():
    from ops.captcha import verify_turnstile

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"success": True}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
        verify_turnstile("token")

    # Verify 5-second timeout is set
    call_args = mock_open.call_args
    assert call_args[1].get("timeout") == 5 or (
        len(call_args[0]) > 1 and call_args[0][1] is None
    )


def test_verify_turnstile_includes_remote_ip():
    from ops.captcha import verify_turnstile

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"success": True}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
        verify_turnstile("token", remote_ip="1.2.3.4")

    call_args = mock_open.call_args
    req = call_args[0][0]
    body = json.loads(req.data.decode())
    assert body.get("remoteip") == "1.2.3.4"


def test_verify_turnstile_exception_returns_false():
    from ops.captcha import verify_turnstile

    with patch("urllib.request.urlopen", side_effect=Exception("unexpected")):
        result = verify_turnstile("token")

    assert result is False
