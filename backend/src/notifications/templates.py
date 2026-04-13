"""HTML and plain-text email templates for lifecycle and admin notifications.

Each function returns a ``(subject, html_body, text_body)`` tuple.
Templates use Python f-strings with inline CSS. No external dependencies.
"""

from __future__ import annotations


def _base_html(title: str, body_content: str) -> str:
    """Wrap content in a basic HTML email layout with inline styles."""
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>{title}</title></head>
<body style="margin:0;padding:0;font-family:Arial,Helvetica,sans-serif;background-color:#f4f4f7;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f7;padding:20px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;">
<tr><td style="background-color:#4f46e5;padding:24px;text-align:center;">
<h1 style="color:#ffffff;margin:0;font-size:24px;">Pixel Prompt</h1>
</td></tr>
<tr><td style="padding:32px 24px;">
{body_content}
</td></tr>
<tr><td style="padding:16px 24px;text-align:center;color:#9ca3af;font-size:12px;">
<p style="margin:0;">Pixel Prompt - AI Image Generation Platform</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def welcome_email(email: str) -> tuple[str, str, str]:
    """Welcome email sent after successful checkout."""
    subject = "Welcome to Pixel Prompt!"
    html = _base_html(
        subject,
        f"""\
<h2 style="color:#1f2937;margin-top:0;">Welcome!</h2>
<p style="color:#4b5563;">Hi {email},</p>
<p style="color:#4b5563;">Thank you for subscribing to Pixel Prompt. Your paid subscription is now \
active and you have full access to all features.</p>
<p style="color:#4b5563;">Start creating amazing images with our AI-powered generation tools.</p>""",
    )
    text = (
        f"Welcome to Pixel Prompt!\n\n"
        f"Hi {email},\n\n"
        f"Thank you for subscribing to Pixel Prompt. Your paid subscription is now "
        f"active and you have full access to all features.\n\n"
        f"Start creating amazing images with our AI-powered generation tools.\n"
    )
    return subject, html, text


def subscription_activated_email(email: str) -> tuple[str, str, str]:
    """Subscription activated confirmation."""
    subject = "Your Pixel Prompt Subscription is Active"
    html = _base_html(
        subject,
        f"""\
<h2 style="color:#1f2937;margin-top:0;">Subscription Active</h2>
<p style="color:#4b5563;">Hi {email},</p>
<p style="color:#4b5563;">Your Pixel Prompt subscription is now active. You have access to \
increased generation limits and all premium features.</p>
<p style="color:#4b5563;">Enjoy creating with Pixel Prompt!</p>""",
    )
    text = (
        f"Your Pixel Prompt Subscription is Active\n\n"
        f"Hi {email},\n\n"
        f"Your Pixel Prompt subscription is now active. You have access to "
        f"increased generation limits and all premium features.\n\n"
        f"Enjoy creating with Pixel Prompt!\n"
    )
    return subject, html, text


def subscription_cancelled_email(email: str) -> tuple[str, str, str]:
    """Subscription cancelled notification."""
    subject = "Your Pixel Prompt Subscription Has Been Cancelled"
    html = _base_html(
        subject,
        f"""\
<h2 style="color:#1f2937;margin-top:0;">Subscription Cancelled</h2>
<p style="color:#4b5563;">Hi {email},</p>
<p style="color:#4b5563;">Your Pixel Prompt subscription has been cancelled. Your account has been \
downgraded to the free tier.</p>
<p style="color:#4b5563;">You can resubscribe at any time to regain access to premium features.</p>""",
    )
    text = (
        f"Your Pixel Prompt Subscription Has Been Cancelled\n\n"
        f"Hi {email},\n\n"
        f"Your Pixel Prompt subscription has been cancelled. Your account has been "
        f"downgraded to the free tier.\n\n"
        f"You can resubscribe at any time to regain access to premium features.\n"
    )
    return subject, html, text


def payment_failed_email(email: str) -> tuple[str, str, str]:
    """Payment failed warning."""
    subject = "Payment Failed - Action Required"
    html = _base_html(
        subject,
        f"""\
<h2 style="color:#1f2937;margin-top:0;">Payment Failed</h2>
<p style="color:#4b5563;">Hi {email},</p>
<p style="color:#4b5563;">We were unable to process your latest payment for Pixel Prompt. \
Please update your payment method to avoid service interruption.</p>
<p style="color:#4b5563;">If you believe this is an error, please contact support.</p>""",
    )
    text = (
        f"Payment Failed - Action Required\n\n"
        f"Hi {email},\n\n"
        f"We were unable to process your latest payment for Pixel Prompt. "
        f"Please update your payment method to avoid service interruption.\n\n"
        f"If you believe this is an error, please contact support.\n"
    )
    return subject, html, text


def suspension_notice_email(email: str, reason: str) -> tuple[str, str, str]:
    """Account suspension notice from admin."""
    subject = "Your Pixel Prompt Account Has Been Suspended"
    html = _base_html(
        subject,
        f"""\
<h2 style="color:#1f2937;margin-top:0;">Account Suspended</h2>
<p style="color:#4b5563;">Hi {email},</p>
<p style="color:#4b5563;">Your Pixel Prompt account has been suspended.</p>
<p style="color:#4b5563;"><strong>Reason:</strong> {reason}</p>
<p style="color:#4b5563;">If you believe this is an error, please contact support.</p>""",
    )
    text = (
        f"Your Pixel Prompt Account Has Been Suspended\n\n"
        f"Hi {email},\n\n"
        f"Your Pixel Prompt account has been suspended.\n\n"
        f"Reason: {reason}\n\n"
        f"If you believe this is an error, please contact support.\n"
    )
    return subject, html, text


def warning_email(email: str, message: str) -> tuple[str, str, str]:
    """Admin warning message to a user."""
    subject = "Important Notice from Pixel Prompt"
    html = _base_html(
        subject,
        f"""\
<h2 style="color:#1f2937;margin-top:0;">Important Notice</h2>
<p style="color:#4b5563;">Hi {email},</p>
<p style="color:#4b5563;">{message}</p>
<p style="color:#4b5563;">If you have questions, please contact support.</p>""",
    )
    text = (
        f"Important Notice from Pixel Prompt\n\n"
        f"Hi {email},\n\n"
        f"{message}\n\n"
        f"If you have questions, please contact support.\n"
    )
    return subject, html, text


def custom_email(email: str, subject: str, message: str) -> tuple[str, str, str]:
    """Admin custom email with user-provided subject and message."""
    html = _base_html(
        subject,
        f"""\
<h2 style="color:#1f2937;margin-top:0;">{subject}</h2>
<p style="color:#4b5563;">Hi {email},</p>
<p style="color:#4b5563;">{message}</p>""",
    )
    text = f"{subject}\n\nHi {email},\n\n{message}\n"
    return subject, html, text
