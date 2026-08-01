"""Tests for billing.stripe_client cached factory."""

from __future__ import annotations

import pytest


def test_get_stripe_raises_when_key_missing(monkeypatch):
    import config
    from billing.stripe_client import get_stripe, reset_stripe_client

    reset_stripe_client()
    monkeypatch.setattr(config, "stripe_secret_key", "")
    with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY"):
        get_stripe()


def test_get_stripe_sets_api_key_once(monkeypatch):
    import stripe as stripe_module

    import config
    from billing.stripe_client import get_stripe, reset_stripe_client

    reset_stripe_client()
    monkeypatch.setattr(config, "stripe_secret_key", "sk_test_abc")
    s = get_stripe()
    assert s is stripe_module
    assert stripe_module.api_key == "sk_test_abc"
    # Cached: subsequent calls do not re-read config.
    monkeypatch.setattr(config, "stripe_secret_key", "sk_test_other")
    s2 = get_stripe()
    assert s2 is stripe_module
    assert stripe_module.api_key == "sk_test_abc"
    reset_stripe_client()


# ---- The upstream call has to be bounded ----
#
# GET /pricing is public, unauthenticated and hit on every page load, and it
# calls Stripe synchronously on a cache miss. stripe-python's default
# RequestsClient timeout is 80 seconds with 2 network retries, so a slow or
# blackholed Stripe holds a Lambda execution for minutes against a 29s
# gateway ceiling and 10 reserved concurrent executions. The caller cannot
# make Stripe slow, but they can repeat the route while it is.


def test_stripe_client_sets_an_explicit_timeout(monkeypatch):
    import stripe as stripe_module

    import config
    from billing.stripe_client import get_stripe, reset_stripe_client

    reset_stripe_client()
    monkeypatch.setattr(config, "stripe_secret_key", "sk_test_abc")
    monkeypatch.setattr(config, "stripe_timeout_seconds", 5.0)
    get_stripe()

    client = stripe_module.default_http_client
    assert client is not None
    assert client._timeout == 5.0
    reset_stripe_client()


def test_stripe_client_bounds_the_retry_budget(monkeypatch):
    """A short timeout multiplied by the default retries is not short."""
    import stripe as stripe_module

    import config
    from billing.stripe_client import get_stripe, reset_stripe_client

    reset_stripe_client()
    monkeypatch.setattr(config, "stripe_secret_key", "sk_test_abc")
    monkeypatch.setattr(config, "stripe_max_network_retries", 1)
    get_stripe()

    assert stripe_module.max_network_retries == 1
    reset_stripe_client()


def test_timeout_is_well_inside_the_gateway_ceiling():
    """The whole point is to answer before the gateway gives up."""
    import config

    assert config.stripe_timeout_seconds > 0
    worst_case = config.stripe_timeout_seconds * (1 + config.stripe_max_network_retries)
    assert worst_case < config.gateway_integration_timeout_seconds
