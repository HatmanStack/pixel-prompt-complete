"""
Configuration module for Pixel Prompt v2.
Loads 4 fixed model configurations with enable/disable support.
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass


def _safe_int(env_var: str, default: int) -> int:
    """Parse int from env var, returning default and warning on bad input."""
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        warnings.warn(
            f"Invalid integer for {env_var}={raw!r}, using default {default}", stacklevel=2
        )
        return default


def _safe_float(env_var: str, default: float) -> float:
    """Parse float from env var, returning default and warning on bad input."""
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        return float(raw)
    except (ValueError, TypeError):
        warnings.warn(f"Invalid float for {env_var}={raw!r}, using default {default}", stacklevel=2)
        return default


@dataclass(frozen=True)
class ModelConfig:
    """Configuration for a single image generation model."""

    name: str  # Internal name: 'gemini', 'nova', 'openai', 'firefly'
    provider: str  # Provider identifier for handler lookup
    enabled: bool
    api_key: str
    model_id: str
    display_name: str  # Human-readable name for UI


# AWS configuration from Lambda execution environment
aws_region = os.environ.get("AWS_REGION", "us-west-2")

# S3 and CloudFront
s3_bucket = os.environ.get("S3_BUCKET")
cloudfront_domain = os.environ.get("CLOUDFRONT_DOMAIN")
if s3_bucket is None:
    warnings.warn("S3_BUCKET not set — storage operations will fail", stacklevel=1)
if cloudfront_domain is None:
    warnings.warn("CLOUDFRONT_DOMAIN not set — CDN URLs will be malformed", stacklevel=1)

# Feature flags (tier system)
auth_enabled = os.environ.get("AUTH_ENABLED", "false").lower() == "true"
billing_enabled = os.environ.get("BILLING_ENABLED", "false").lower() == "true"
if billing_enabled and not auth_enabled:
    raise RuntimeError("BILLING_ENABLED=true requires AUTH_ENABLED=true")

# Feature flags (operational safety)
captcha_enabled = os.environ.get("CAPTCHA_ENABLED", "false").lower() == "true"
ses_enabled = os.environ.get("SES_ENABLED", "false").lower() == "true"
admin_enabled = os.environ.get("ADMIN_ENABLED", "false").lower() == "true"
if admin_enabled and not auth_enabled:
    raise RuntimeError("ADMIN_ENABLED=true requires AUTH_ENABLED=true")

# Cognito
cognito_user_pool_id = os.environ.get("COGNITO_USER_POOL_ID", "")
cognito_user_pool_client_id = os.environ.get("COGNITO_USER_POOL_CLIENT_ID", "")
cognito_domain = os.environ.get("COGNITO_DOMAIN", "")
cognito_region = os.environ.get("COGNITO_REGION", "us-west-2")

# DynamoDB
users_table_name = os.environ.get("USERS_TABLE_NAME", "pixel-prompt-users")

# Guest tracking
guest_token_secret = os.environ.get("GUEST_TOKEN_SECRET", "")
if auth_enabled and not guest_token_secret:
    raise RuntimeError(
        "AUTH_ENABLED=true requires GUEST_TOKEN_SECRET to be set. "
        "Without it, guest tracking is disabled and unauthenticated requests "
        "will bypass quota enforcement."
    )
guest_generate_limit = _safe_int("GUEST_GENERATE_LIMIT", 1)
guest_window_seconds = _safe_int("GUEST_WINDOW_SECONDS", 3600)
guest_global_limit = _safe_int("GUEST_GLOBAL_LIMIT", 5)
guest_global_window_seconds = _safe_int("GUEST_GLOBAL_WINDOW_SECONDS", 3600)

# Free tier
free_generate_limit = _safe_int("FREE_GENERATE_LIMIT", 1)
free_refine_limit = _safe_int("FREE_REFINE_LIMIT", 2)
free_window_seconds = _safe_int("FREE_WINDOW_SECONDS", 3600)

# Paid tier
paid_daily_limit = _safe_int("PAID_DAILY_LIMIT", 200)
paid_window_seconds = _safe_int("PAID_WINDOW_SECONDS", 86400)

# Stripe
stripe_secret_key = os.environ.get("STRIPE_SECRET_KEY", "")
stripe_webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
if billing_enabled:
    if not stripe_secret_key:
        raise RuntimeError("BILLING_ENABLED=true requires STRIPE_SECRET_KEY to be set")
    if not stripe_webhook_secret:
        raise RuntimeError("BILLING_ENABLED=true requires STRIPE_WEBHOOK_SECRET to be set")
stripe_price_id = os.environ.get("STRIPE_PRICE_ID", "")
stripe_success_url = os.environ.get("STRIPE_SUCCESS_URL", "")
stripe_cancel_url = os.environ.get("STRIPE_CANCEL_URL", "")
stripe_portal_return_url = os.environ.get("STRIPE_PORTAL_RETURN_URL", "")

# Prompt enhancement model configuration
prompt_model_provider = os.environ.get("PROMPT_MODEL_PROVIDER", "openai")
prompt_model_id = os.environ.get("PROMPT_MODEL_ID", "gpt-4o")
prompt_model_api_key = os.environ.get("PROMPT_MODEL_API_KEY", "")

# Firefly OAuth2 credentials (used by adobe_firefly provider)
firefly_client_id = os.environ.get("FIREFLY_CLIENT_ID", "")
firefly_client_secret = os.environ.get("FIREFLY_CLIENT_SECRET", "")

# 4 Fixed Models Configuration
_gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
_openai_api_key = os.environ.get("OPENAI_API_KEY", "")

MODELS: dict[str, ModelConfig] = {
    "gemini": ModelConfig(
        name="gemini",
        provider="google_gemini",
        enabled=(
            os.environ.get("GEMINI_ENABLED", "true").lower() == "true" and bool(_gemini_api_key)
        ),
        api_key=_gemini_api_key,
        model_id=os.environ.get("GEMINI_MODEL_ID", "gemini-3.1-flash-image-preview"),
        display_name="Gemini",
    ),
    "nova": ModelConfig(
        name="nova",
        provider="bedrock_nova",
        enabled=os.environ.get("NOVA_ENABLED", "true").lower() == "true",
        api_key="",  # Auth via IAM role
        model_id=os.environ.get("NOVA_MODEL_ID", "amazon.nova-canvas-v1:0"),
        display_name="Nova Canvas",
    ),
    "openai": ModelConfig(
        name="openai",
        provider="openai",
        enabled=(
            os.environ.get("OPENAI_ENABLED", "true").lower() == "true" and bool(_openai_api_key)
        ),
        api_key=_openai_api_key,
        model_id=os.environ.get("OPENAI_MODEL_ID", "dall-e-3"),
        display_name="DALL-E 3",
    ),
    "firefly": ModelConfig(
        name="firefly",
        provider="adobe_firefly",
        enabled=(
            os.environ.get("FIREFLY_ENABLED", "true").lower() == "true"
            and bool(firefly_client_id)
            and bool(firefly_client_secret)
        ),
        api_key="",  # Auth via OAuth2 client credentials
        model_id=os.environ.get("FIREFLY_MODEL_ID", "firefly-image-5"),
        display_name="Firefly",
    ),
}

# CORS
cors_allowed_origin = os.environ.get("CORS_ALLOWED_ORIGIN", "*")

# Iteration limits
MAX_ITERATIONS = 7
ITERATION_WARNING_THRESHOLD = 5


def get_enabled_models() -> list[ModelConfig]:
    """Return list of enabled ModelConfig objects."""
    return [model for model in MODELS.values() if model.enabled]


def get_model(name: str) -> ModelConfig:
    """
    Get specific model config by name.

    Args:
        name: Model name ('gemini', 'nova', 'openai', 'firefly')

    Returns:
        ModelConfig for the requested model

    Raises:
        ValueError: If model name is invalid or model is disabled
    """
    if name not in MODELS:
        raise ValueError(f"Unknown model: {name}. Valid models: {list(MODELS.keys())}")

    model = MODELS[name]
    if not model.enabled:
        raise ValueError(f"Model '{name}' is disabled")

    return model


def get_model_config_dict(model: ModelConfig) -> dict:
    """
    Convert ModelConfig to dict format expected by handlers.

    Returns:
        Dict with 'id', 'api_key', and provider-specific fields
    """
    config = {
        "id": model.model_id,
        "provider": model.provider,
    }
    config["api_key"] = model.api_key
    if model.provider == "adobe_firefly":
        config["client_id"] = firefly_client_id
        config["client_secret"] = firefly_client_secret
    return config


# Per-model daily cost ceiling caps
model_gemini_daily_cap = _safe_int("MODEL_GEMINI_DAILY_CAP", 500)
model_nova_daily_cap = _safe_int("MODEL_NOVA_DAILY_CAP", 500)
model_openai_daily_cap = _safe_int("MODEL_OPENAI_DAILY_CAP", 500)
model_firefly_daily_cap = _safe_int("MODEL_FIREFLY_DAILY_CAP", 500)

MODEL_DAILY_CAPS: dict[str, int] = {
    "gemini": model_gemini_daily_cap,
    "nova": model_nova_daily_cap,
    "openai": model_openai_daily_cap,
    "firefly": model_firefly_daily_cap,
}

# ---------------------------------------------------------------------------
# Cost table: what a provider call costs US, in micro-dollars (1e-6 USD).
#
# Integers, never floats: these feed DynamoDB atomic counters, and float
# accumulation would drift. Seeded from public rate cards — replace with
# measured spend before committing to any public price. Correcting them is a
# config change, not a code change, which is the whole point of the table.
# ---------------------------------------------------------------------------
_DEFAULT_MODEL_COSTS_USD_MICROS: dict[str, int] = {
    "gemini": 39000,   # $0.039
    "nova": 40000,     # $0.040
    "openai": 40000,   # $0.040
    "firefly": 70000,  # $0.070 (credit-based; least certain of the four)
}

# An iterate/outpaint call generates one image, same as a generate call, so the
# per-operation defaults match. They are separate env vars because providers
# price edits differently (OpenAI iteration uses gpt-image-1, not dall-e-3).
COST_OPERATIONS: tuple[str, ...] = ("generate", "refine", "outpaint")

MODEL_COSTS_USD_MICROS: dict[str, dict[str, int]] = {
    model: {
        op: _safe_int(f"COST_{model.upper()}_{op.upper()}_USD_MICROS", default)
        for op in COST_OPERATIONS
    }
    for model, default in _DEFAULT_MODEL_COSTS_USD_MICROS.items()
}

# gpt-4o prompt adaptation, charged once per /generate and once per /enhance.
enhance_cost_usd_micros = _safe_int("COST_ENHANCE_USD_MICROS", 7000)


def model_cost_micros(model_name: str, operation: str) -> int:
    """Cost in micro-dollars of one ``operation`` on ``model_name``.

    Unknown models/operations cost 0 rather than raising: a mispriced meter
    is a reporting bug, but an exception here would fail a user's request.
    The zero shows up as an obvious gap in the spend dashboard.
    """
    return MODEL_COSTS_USD_MICROS.get(model_name, {}).get(operation, 0)


# ---------------------------------------------------------------------------
# Global daily spend ceiling, in micro-dollars.
#
# Defaults to $100/day ON, deliberately. Every other guard in this system is
# conditional on AUTH_ENABLED, which defaults false — so a default deploy had
# no spend bound of any kind. This one applies unconditionally and is the last
# thing between a misconfiguration and an unbounded provider bill.
#
# Set to 0 to disable, consciously.
# ---------------------------------------------------------------------------
global_daily_spend_ceiling_usd_micros = _safe_int(
    "GLOBAL_DAILY_SPEND_CEILING_USD_MICROS", 100_000_000
)

# Sub-ceiling for /enhance specifically, in micro-dollars. Default $5/day.
#
# /enhance is unauthenticated, captcha-free and unquota'd (closing that is
# P0-D). Metering it against the shared global budget alone would let anonymous
# traffic exhaust the day's spend and 503 /generate for paying users — turning
# a cost guard into a denial-of-service amplifier. This bounds what the open
# endpoint can consume, independently of the global ceiling it also respects.
#
# Set to 0 to disable this sub-ceiling (the global one still applies).
enhance_daily_spend_ceiling_usd_micros = _safe_int(
    "ENHANCE_DAILY_SPEND_CEILING_USD_MICROS", 5_000_000
)

# CAPTCHA (Cloudflare Turnstile)
turnstile_secret_key = os.environ.get("TURNSTILE_SECRET_KEY", "")
if captcha_enabled and not turnstile_secret_key:
    raise RuntimeError("CAPTCHA_ENABLED=true requires TURNSTILE_SECRET_KEY to be set")

# SES email notifications
ses_from_email = os.environ.get("SES_FROM_EMAIL", "")
ses_region = os.environ.get("SES_REGION", "us-west-2")
if ses_enabled and not ses_from_email:
    raise RuntimeError("SES_ENABLED=true requires SES_FROM_EMAIL to be set")

# CORS + Auth compatibility check
if auth_enabled and cors_allowed_origin == "*":
    from utils.logger import StructuredLogger as _CfgLogger

    _CfgLogger.warning(
        "CORS_ALLOWED_ORIGIN='*' with AUTH_ENABLED=true: "
        "browsers will block credentialed requests. "
        "Set CORS_ALLOWED_ORIGIN to your frontend domain."
    )

# Operational Timeouts (seconds) - configurable via environment
api_client_timeout = _safe_float("API_CLIENT_TIMEOUT", 60.0)
image_download_timeout = _safe_int("IMAGE_DOWNLOAD_TIMEOUT", 30)
enhance_timeout = _safe_float("ENHANCE_TIMEOUT", 30.0)
generate_thread_workers = _safe_int("GENERATE_THREAD_WORKERS", 4)
