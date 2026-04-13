"""Tests for SES client and email sender."""

from __future__ import annotations

import importlib
import os

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

FROM_EMAIL = "noreply@example.com"
SES_REGION = "us-east-1"


@pytest.fixture
def ses_on(monkeypatch):
    """Enable SES for testing."""
    monkeypatch.setenv("SES_ENABLED", "true")
    monkeypatch.setenv("SES_FROM_EMAIL", FROM_EMAIL)
    monkeypatch.setenv("SES_REGION", SES_REGION)
    import config
    importlib.reload(config)
    yield
    monkeypatch.delenv("SES_ENABLED", raising=False)
    monkeypatch.delenv("SES_FROM_EMAIL", raising=False)
    monkeypatch.delenv("SES_REGION", raising=False)
    importlib.reload(config)


@pytest.fixture
def ses_off(monkeypatch):
    """Disable SES for testing."""
    monkeypatch.setenv("SES_ENABLED", "false")
    import config
    importlib.reload(config)
    yield
    importlib.reload(config)


class TestGetSesClient:
    def test_returns_cached_ses_client(self, ses_on):
        with mock_aws():
            from notifications.ses_client import get_ses_client, reset_ses_client
            reset_ses_client()
            client1 = get_ses_client()
            client2 = get_ses_client()
            assert client1 is client2
            reset_ses_client()

    def test_raises_runtime_error_when_disabled(self, ses_off):
        from notifications.ses_client import get_ses_client, reset_ses_client
        reset_ses_client()
        with pytest.raises(RuntimeError, match="SES is not enabled"):
            get_ses_client()
        reset_ses_client()


class TestSendEmail:
    def test_returns_false_when_disabled(self, ses_off):
        from notifications.sender import send_email
        result = send_email("user@example.com", "Test", "<p>Hi</p>", "Hi")
        assert result is False

    def test_returns_true_on_success(self, ses_on):
        with mock_aws():
            # Verify the sender identity in SES mock
            ses = boto3.client("ses", region_name=SES_REGION)
            ses.verify_email_identity(EmailAddress=FROM_EMAIL)

            from notifications.ses_client import reset_ses_client
            reset_ses_client()

            from notifications.sender import send_email
            result = send_email(
                "user@example.com",
                "Welcome",
                "<p>Welcome!</p>",
                "Welcome!",
            )
            assert result is True
            reset_ses_client()

    def test_returns_false_on_ses_error(self, ses_on, monkeypatch):
        from notifications.ses_client import reset_ses_client
        reset_ses_client()

        from notifications import sender

        def fake_get_client():
            raise RuntimeError("SES client error")

        monkeypatch.setattr(sender, "get_ses_client", fake_get_client)
        result = sender.send_email("user@example.com", "Test", "<p>Hi</p>", "Hi")
        assert result is False
        reset_ses_client()

    def test_does_not_raise_on_error(self, ses_on, monkeypatch):
        """send_email must never raise (fire-and-forget)."""
        from notifications.ses_client import reset_ses_client
        reset_ses_client()

        from notifications import sender

        def fake_get_client():
            raise RuntimeError("boom")

        monkeypatch.setattr(sender, "get_ses_client", fake_get_client)
        # Should not raise
        result = sender.send_email("user@example.com", "Test", "<p>Hi</p>", "Hi")
        assert result is False
        reset_ses_client()
