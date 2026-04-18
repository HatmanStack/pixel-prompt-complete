"""Tests for tier feature flags and quota env vars in config.py."""

from __future__ import annotations

import importlib

import pytest


def _reload_config():
    import config

    return importlib.reload(config)


@pytest.fixture(autouse=True)
def _reset_auth_billing_env(monkeypatch):
    """Ensure auth/billing flags are cleared before each test for hermetic runs."""
    for var in ("AUTH_ENABLED", "BILLING_ENABLED", "GUEST_TOKEN_SECRET",
                "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
                "CAPTCHA_ENABLED", "TURNSTILE_SECRET_KEY",
                "SES_ENABLED", "SES_FROM_EMAIL",
                "ADMIN_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    yield
    _reload_config()


def test_default_flags_false(monkeypatch):
    for var in ("AUTH_ENABLED", "BILLING_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    config = _reload_config()
    assert config.auth_enabled is False
    assert config.billing_enabled is False


def test_auth_only_valid(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "test-secret")
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    config = _reload_config()
    assert config.auth_enabled is True
    assert config.billing_enabled is False


def test_auth_without_guest_secret_raises(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "")
    with pytest.raises(RuntimeError, match="GUEST_TOKEN_SECRET"):
        _reload_config()
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    _reload_config()


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


# --- Phase 1: Cost ceiling, CAPTCHA, SES, Admin feature flags ---


def test_captcha_enabled_defaults_false(monkeypatch):
    monkeypatch.delenv("CAPTCHA_ENABLED", raising=False)
    config = _reload_config()
    assert config.captcha_enabled is False


def test_captcha_enabled_true_without_secret_raises(monkeypatch):
    monkeypatch.setenv("CAPTCHA_ENABLED", "true")
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "")
    with pytest.raises(RuntimeError, match="TURNSTILE_SECRET_KEY"):
        _reload_config()
    monkeypatch.delenv("CAPTCHA_ENABLED", raising=False)
    _reload_config()


def test_admin_enabled_without_auth_raises(monkeypatch):
    monkeypatch.setenv("ADMIN_ENABLED", "true")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    with pytest.raises(RuntimeError, match="ADMIN_ENABLED=true requires AUTH_ENABLED=true"):
        _reload_config()
    monkeypatch.delenv("ADMIN_ENABLED", raising=False)
    _reload_config()


def test_ses_enabled_without_email_raises(monkeypatch):
    monkeypatch.setenv("SES_ENABLED", "true")
    monkeypatch.setenv("SES_FROM_EMAIL", "")
    with pytest.raises(RuntimeError, match="SES_FROM_EMAIL"):
        _reload_config()
    monkeypatch.delenv("SES_ENABLED", raising=False)
    _reload_config()


def test_model_daily_caps_dict_has_all_models(monkeypatch):
    for var in ("MODEL_GEMINI_DAILY_CAP", "MODEL_NOVA_DAILY_CAP",
                "MODEL_OPENAI_DAILY_CAP", "MODEL_FIREFLY_DAILY_CAP"):
        monkeypatch.delenv(var, raising=False)
    config = _reload_config()
    assert set(config.MODEL_DAILY_CAPS.keys()) == {"gemini", "nova", "openai", "firefly"}


def test_per_model_cap_defaults_to_500(monkeypatch):
    for var in ("MODEL_GEMINI_DAILY_CAP", "MODEL_NOVA_DAILY_CAP",
                "MODEL_OPENAI_DAILY_CAP", "MODEL_FIREFLY_DAILY_CAP"):
        monkeypatch.delenv(var, raising=False)
    config = _reload_config()
    for model_name, cap in config.MODEL_DAILY_CAPS.items():
        assert cap == 500, f"{model_name} cap should be 500, got {cap}"


def test_per_model_cap_override(monkeypatch):
    monkeypatch.setenv("MODEL_GEMINI_DAILY_CAP", "100")
    config = _reload_config()
    assert config.MODEL_DAILY_CAPS["gemini"] == 100


def test_cors_wildcard_with_auth_warns(monkeypatch):
    """CORS_ALLOWED_ORIGIN='*' with AUTH_ENABLED=true should emit a warning."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "test-secret")
    monkeypatch.setenv("CORS_ALLOWED_ORIGIN", "*")
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        config = _reload_config()
        cors_warnings = [x for x in w if "CORS_ALLOWED_ORIGIN" in str(x.message)]
        assert len(cors_warnings) == 1
        assert "credentialed requests" in str(cors_warnings[0].message)


def test_cors_specific_origin_with_auth_no_warning(monkeypatch):
    """No warning when CORS_ALLOWED_ORIGIN is set to a specific domain."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "test-secret")
    monkeypatch.setenv("CORS_ALLOWED_ORIGIN", "https://example.com")
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        config = _reload_config()
        cors_warnings = [x for x in w if "CORS_ALLOWED_ORIGIN" in str(x.message)]
        assert len(cors_warnings) == 0


def test_cors_wildcard_without_auth_no_warning(monkeypatch):
    """No warning when AUTH_ENABLED=false even with wildcard CORS."""
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("CORS_ALLOWED_ORIGIN", "*")
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        config = _reload_config()
        cors_warnings = [x for x in w if "CORS_ALLOWED_ORIGIN" in str(x.message)]
        assert len(cors_warnings) == 0
