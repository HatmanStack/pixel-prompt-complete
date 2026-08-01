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
    assert client._timeout == (2.0, 3.0)
    reset_stripe_client()


def test_the_timeout_is_a_pair_that_sums_to_the_budget(monkeypatch):
    """A scalar is applied per phase, so it buys double what it reads as.

    `requests` uses one scalar for BOTH the connect and the read timeout, so
    timeout=5.0 permits 10s per attempt. Splitting it explicitly is what makes
    STRIPE_TIMEOUT_SECONDS mean the whole budget for one attempt.
    """
    import config
    from billing.stripe_client import stripe_timeout_pair

    monkeypatch.setattr(config, "stripe_timeout_seconds", 5.0)
    connect, read = stripe_timeout_pair()
    assert connect + read == 5.0
    assert connect > 0 and read > 0

    monkeypatch.setattr(config, "stripe_timeout_seconds", 1.0)
    connect, read = stripe_timeout_pair()
    assert connect + read == 1.0
    assert connect > 0 and read > 0


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


def test_worst_case_is_well_inside_the_gateway_ceiling():
    """Computed from what requests actually does, not from the scalar.

    An earlier version of this asserted `timeout * (1 + retries)`, which is
    the number the code was written against rather than the one the HTTP
    client produces -- so it passed while the property it names did not hold.
    Per attempt the cost is connect + read; attempts are 1 + retries; and
    Stripe sleeps between them.
    """
    import config
    from billing.stripe_client import stripe_timeout_pair

    connect, read = stripe_timeout_pair()
    per_attempt = connect + read
    attempts = 1 + config.stripe_max_network_retries
    # Stripe's initial retry delay is 0.5s and doubles; allow a second per gap.
    backoff_allowance = config.stripe_max_network_retries * 1.0

    worst_case = per_attempt * attempts + backoff_allowance
    assert worst_case < config.gateway_integration_timeout_seconds, worst_case


def test_a_zero_timeout_is_refused_at_import(monkeypatch):
    """`requests` reads 0 as "fail immediately", not "no timeout".

    An operator setting StripeTimeoutSeconds=0 to restore the SDK's previous
    unbounded behaviour would 500 every checkout instead. Caught at deploy,
    matching the credit-ledger knobs, rather than at the till.
    """
    import importlib

    import config

    monkeypatch.setenv("STRIPE_TIMEOUT_SECONDS", "0")
    with pytest.raises(RuntimeError, match="STRIPE_TIMEOUT_SECONDS"):
        importlib.reload(config)

    monkeypatch.delenv("STRIPE_TIMEOUT_SECONDS", raising=False)
    importlib.reload(config)
    assert config.stripe_timeout_seconds > 0
