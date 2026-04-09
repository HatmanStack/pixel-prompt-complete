"""Cached Stripe client factory.

The ``stripe`` module is a singleton — setting ``stripe.api_key`` mutates
global state. Wrapping it in an ``lru_cache`` ensures we set the key exactly
once per Lambda container and raise cleanly if it is unset.
"""

from __future__ import annotations

from functools import lru_cache

import stripe

import config


@lru_cache(maxsize=1)
def get_stripe():
    """Return the configured ``stripe`` module.

    Raises:
        RuntimeError: if ``STRIPE_SECRET_KEY`` is not configured.
    """
    if not config.stripe_secret_key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured")
    stripe.api_key = config.stripe_secret_key
    return stripe


def reset_stripe_client() -> None:
    """Clear the cached client (for tests)."""
    get_stripe.cache_clear()
