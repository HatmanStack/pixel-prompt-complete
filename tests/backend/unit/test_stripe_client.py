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
    import config
    import stripe as stripe_module
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
