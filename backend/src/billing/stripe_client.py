"""Cached Stripe client factory.

The ``stripe`` module is a singleton — setting ``stripe.api_key`` mutates
global state. Wrapping it in an ``lru_cache`` ensures we set the key exactly
once per Lambda container and raise cleanly if it is unset.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import stripe

import config


@lru_cache(maxsize=1)
def get_stripe() -> Any:
    """Return the configured ``stripe`` module.

    Also bounds how long a Stripe call may hold the execution. The SDK's
    default ``RequestsClient`` timeout is **80 seconds** and it retries twice,
    so an unbounded call can occupy a Lambda for four minutes against a 29s
    gateway ceiling and 10 reserved concurrent executions.

    That matters most on ``GET /pricing``, which is public, unauthenticated
    and hit on every page load: a caller cannot make Stripe slow, but they
    can repeat the route while it is, and each repeat pins another execution
    from a pool the paid endpoints share.

    The retry budget is set alongside the timeout because they multiply --
    a 5s timeout with the default two retries is a 15s worst case, and
    bounding one without the other only looks bounded.

    Raises:
        RuntimeError: if ``STRIPE_SECRET_KEY`` is not configured.
    """
    if not config.stripe_secret_key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured")
    stripe.api_key = config.stripe_secret_key
    stripe.max_network_retries = config.stripe_max_network_retries
    stripe.default_http_client = stripe.new_default_http_client(timeout=stripe_timeout_pair())
    return stripe


def stripe_timeout_pair() -> tuple[float, float]:
    """The (connect, read) budget for one Stripe attempt.

    A scalar is the obvious thing to pass and it is wrong: ``requests``
    applies one to the connect phase and the read phase **separately**, so
    ``timeout=5.0`` permits 10 seconds per attempt. With retries on top, the
    real worst case was about double what the config comment and the guard
    test computed -- and the guard passed regardless, because it was derived
    from the same wrong model as the code.

    Splitting it explicitly makes ``stripe_timeout_seconds`` mean what it
    says: the whole budget for one attempt. Connect gets the smaller share
    because a TCP handshake that has not completed in two seconds is not going
    to; the remainder goes to the read, which is where a slow Stripe actually
    shows up.
    """
    total = config.stripe_timeout_seconds
    connect = min(2.0, total / 2)
    return (connect, total - connect)


def reset_stripe_client() -> None:
    """Clear the cached client (for tests)."""
    get_stripe.cache_clear()
