"""Cached SES client factory.

Follows the same caching pattern as ``billing/stripe_client.py``.
The client is created once per Lambda container and reused.
"""

from __future__ import annotations

from functools import lru_cache

import boto3

import config


@lru_cache(maxsize=1)
def get_ses_client():
    """Return a cached boto3 SES client.

    Raises:
        RuntimeError: if ``SES_ENABLED`` is not ``true``.
    """
    if not config.ses_enabled:
        raise RuntimeError("SES is not enabled")
    return boto3.client("ses", region_name=config.ses_region)


def reset_ses_client() -> None:
    """Clear the cached client (for tests)."""
    get_ses_client.cache_clear()
