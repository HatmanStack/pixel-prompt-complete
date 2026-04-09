"""Tests for tier feature flags and quota env vars in config.py."""

from __future__ import annotations

import importlib

import pytest


def _reload_config():
    import config

    return importlib.reload(config)


def test_default_flags_false(monkeypatch):
    for var in ("AUTH_ENABLED", "BILLING_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    config = _reload_config()
    assert config.auth_enabled is False
    assert config.billing_enabled is False


def test_auth_only_valid(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    config = _reload_config()
    assert config.auth_enabled is True
    assert config.billing_enabled is False


def test_billing_without_auth_raises(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("BILLING_ENABLED", "true")
    with pytest.raises(RuntimeError, match="BILLING_ENABLED=true requires AUTH_ENABLED=true"):
        _reload_config()
    # restore clean state for later tests
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    _reload_config()


def test_quota_env_vars_defaults(monkeypatch):
    for var in (
        "GUEST_GENERATE_LIMIT",
        "GUEST_WINDOW_SECONDS",
        "GUEST_GLOBAL_LIMIT",
        "GUEST_GLOBAL_WINDOW_SECONDS",
        "FREE_GENERATE_LIMIT",
        "FREE_REFINE_LIMIT",
        "FREE_WINDOW_SECONDS",
        "PAID_DAILY_LIMIT",
        "PAID_WINDOW_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)
    config = _reload_config()
    assert config.guest_generate_limit == 1
    assert config.guest_window_seconds == 3600
    assert config.guest_global_limit == 5
    assert config.guest_global_window_seconds == 3600
    assert config.free_generate_limit == 1
    assert config.free_refine_limit == 2
    assert config.free_window_seconds == 3600
    assert config.paid_daily_limit == 200
    assert config.paid_window_seconds == 86400


def test_quota_env_var_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("FREE_REFINE_LIMIT", "not-an-int")
    config = _reload_config()
    assert config.free_refine_limit == 2


def test_quota_env_var_override(monkeypatch):
    monkeypatch.setenv("FREE_REFINE_LIMIT", "9")
    config = _reload_config()
    assert config.free_refine_limit == 9


def test_old_rate_limit_constants_removed(monkeypatch):
    for var in ("GLOBAL_LIMIT", "IP_LIMIT", "IP_INCLUDE"):
        monkeypatch.delenv(var, raising=False)
    config = _reload_config()
    assert not hasattr(config, "global_limit")
    assert not hasattr(config, "ip_limit")
    assert not hasattr(config, "ip_include")
