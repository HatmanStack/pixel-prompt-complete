"""Tests for email templates."""

from __future__ import annotations

import re

import pytest


def _has_no_html_tags(text: str) -> bool:
    """Return True if text contains no HTML tags."""
    return not re.search(r"<[^>]+>", text)


class TestBaseHtml:
    def test_wraps_content_in_html_tags(self):
        from notifications.templates import _base_html

        result = _base_html("Test Title", "<p>Body content</p>")
        assert "<html" in result
        assert "</html>" in result
        assert "Test Title" in result
        assert "Body content" in result


class TestWelcomeEmail:
    def test_returns_3_tuple(self):
        from notifications.templates import welcome_email

        result = welcome_email("user@example.com")
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_subject_is_string(self):
        from notifications.templates import welcome_email

        subject, _, _ = welcome_email("user@example.com")
        assert isinstance(subject, str)
        assert len(subject) > 0

    def test_html_contains_email(self):
        from notifications.templates import welcome_email

        _, html, _ = welcome_email("user@example.com")
        assert "user@example.com" in html

    def test_text_has_no_html_tags(self):
        from notifications.templates import welcome_email

        _, _, text = welcome_email("user@example.com")
        assert _has_no_html_tags(text)


class TestSubscriptionActivatedEmail:
    def test_returns_3_tuple(self):
        from notifications.templates import subscription_activated_email

        result = subscription_activated_email("user@example.com")
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_html_contains_email(self):
        from notifications.templates import subscription_activated_email

        _, html, _ = subscription_activated_email("user@example.com")
        assert "user@example.com" in html

    def test_text_has_no_html_tags(self):
        from notifications.templates import subscription_activated_email

        _, _, text = subscription_activated_email("user@example.com")
        assert _has_no_html_tags(text)


class TestSubscriptionCancelledEmail:
    def test_returns_3_tuple(self):
        from notifications.templates import subscription_cancelled_email

        result = subscription_cancelled_email("user@example.com")
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_text_has_no_html_tags(self):
        from notifications.templates import subscription_cancelled_email

        _, _, text = subscription_cancelled_email("user@example.com")
        assert _has_no_html_tags(text)


class TestPaymentFailedEmail:
    def test_returns_3_tuple(self):
        from notifications.templates import payment_failed_email

        result = payment_failed_email("user@example.com")
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_text_has_no_html_tags(self):
        from notifications.templates import payment_failed_email

        _, _, text = payment_failed_email("user@example.com")
        assert _has_no_html_tags(text)


class TestSuspensionNoticeEmail:
    def test_returns_3_tuple(self):
        from notifications.templates import suspension_notice_email

        result = suspension_notice_email("user@example.com", "Terms violation")
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_html_contains_reason(self):
        from notifications.templates import suspension_notice_email

        _, html, _ = suspension_notice_email("user@example.com", "Terms violation")
        assert "Terms violation" in html

    def test_text_contains_reason(self):
        from notifications.templates import suspension_notice_email

        _, _, text = suspension_notice_email("user@example.com", "Terms violation")
        assert "Terms violation" in text
        assert _has_no_html_tags(text)


class TestWarningEmail:
    def test_returns_3_tuple(self):
        from notifications.templates import warning_email

        result = warning_email("user@example.com", "Your usage is high")
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_html_contains_message(self):
        from notifications.templates import warning_email

        _, html, _ = warning_email("user@example.com", "Your usage is high")
        assert "Your usage is high" in html

    def test_text_has_no_html_tags(self):
        from notifications.templates import warning_email

        _, _, text = warning_email("user@example.com", "Your usage is high")
        assert _has_no_html_tags(text)


class TestCustomEmail:
    def test_returns_3_tuple(self):
        from notifications.templates import custom_email

        result = custom_email("user@example.com", "Custom Subject", "Custom message body")
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_subject_matches_input(self):
        from notifications.templates import custom_email

        subject, _, _ = custom_email("user@example.com", "Custom Subject", "Custom message body")
        assert subject == "Custom Subject"

    def test_html_contains_message(self):
        from notifications.templates import custom_email

        _, html, _ = custom_email("user@example.com", "Custom Subject", "Custom message body")
        assert "Custom message body" in html

    def test_text_has_no_html_tags(self):
        from notifications.templates import custom_email

        _, _, text = custom_email("user@example.com", "Custom Subject", "Custom message body")
        assert _has_no_html_tags(text)


class TestAllTemplatesCallable:
    """Verify all 7 template functions exist and are callable."""

    def test_all_functions_exist(self):
        from notifications import templates

        expected = [
            "welcome_email",
            "subscription_activated_email",
            "subscription_cancelled_email",
            "payment_failed_email",
            "suspension_notice_email",
            "warning_email",
            "custom_email",
        ]
        for name in expected:
            fn = getattr(templates, name, None)
            assert fn is not None, f"Missing template function: {name}"
            assert callable(fn), f"Not callable: {name}"
