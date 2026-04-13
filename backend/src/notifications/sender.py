"""Fire-and-forget email sender via Amazon SES.

If ``SES_ENABLED=false``, all sends are no-ops that return ``False``.
Errors are logged but never raised.
"""

from __future__ import annotations

import config
from notifications.ses_client import get_ses_client
from utils.logger import StructuredLogger


def send_email(to: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send an email via SES.

    Returns ``True`` on success, ``False`` when disabled or on any error.
    Never raises.
    """
    if not config.ses_enabled:
        return False

    try:
        client = get_ses_client()
        client.send_email(
            Source=config.ses_from_email,
            Destination={"ToAddresses": [to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": html_body, "Charset": "UTF-8"},
                    "Text": {"Data": text_body, "Charset": "UTF-8"},
                },
            },
        )
        return True
    except Exception as e:
        StructuredLogger.error(f"Failed to send email to {to}: {e}")
        return False
