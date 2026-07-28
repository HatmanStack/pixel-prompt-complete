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
# AUTH_ENABLED has NO default, deliberately.
#
# There is no safe value to guess. "false" serves unauthenticated traffic;
# "true" requires Cognito and a guest secret. Defaulting to either quietly
# picks a security posture on the operator's behalf, and the audit that
# prompted this found exactly that: a stack deployed open because nobody
# decided it should be.
#
# Failing at import is the point — the choice has to appear in the deploy
# parameters, where it is reviewable.
_auth_raw = os.environ.get("AUTH_ENABLED")
if _auth_raw is None:
    raise RuntimeError(
        "AUTH_ENABLED must be set explicitly to 'true' or 'false'. "
        "There is no safe default: 'false' serves unauthenticated traffic, "
        "'true' requires Cognito. Set it in the deploy parameters."
    )
if _auth_raw.lower() not in ("true", "false"):
    raise RuntimeError(
        f"AUTH_ENABLED must be 'true' or 'false', got {_auth_raw!r}. "
        "Anything else silently reads as 'false', i.e. unauthenticated."
    )
auth_enabled = _auth_raw.lower() == "true"
billing_enabled = os.environ.get("BILLING_ENABLED", "false").lower() == "true"
if billing_enabled and not auth_enabled:
    raise RuntimeError("BILLING_ENABLED=true requires AUTH_ENABLED=true")

# Feature flags (operational safety)
captcha_enabled = os.environ.get("CAPTCHA_ENABLED", "false").lower() == "true"

# Age gate. Defaults to ON, unlike every other feature flag here, because the
# provider terms require it rather than merely permitting it: Google allows its
# API only where the calling service is not "likely to be accessed by"
# under-18s. An operator who sets nothing should get the compliant behaviour,
# so disabling is the explicit act.
age_gate_enabled = os.environ.get("AGE_GATE_ENABLED", "true").lower() == "true"
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
# Per-IP guest limit. The per-token limit below bounds nothing on its own:
# a guest identity is a cookie, and dropping it mints a fresh one with a fresh
# counter. This is the bucket a cookie drop cannot escape.
#
# What it actually protects is FAIRNESS, not total spend — GUEST_GLOBAL_LIMIT
# already caps aggregate guest cost. Without a per-IP bucket, one caller
# cycling cookies can drain the entire global pool and lock out every other
# guest. Keep this BELOW the global limit or it can never bind first.
#
# More generous than the per-token limit on purpose: an IP is not a person,
# since offices and mobile carriers NAT many users behind one address. It is
# an abuse ceiling, not a fair-use quota.
guest_ip_generate_limit = _safe_int("GUEST_IP_GENERATE_LIMIT", 3)
guest_ip_window_seconds = _safe_int("GUEST_IP_WINDOW_SECONDS", 3600)

guest_global_limit = _safe_int("GUEST_GLOBAL_LIMIT", 5)
guest_global_window_seconds = _safe_int("GUEST_GLOBAL_WINDOW_SECONDS", 3600)

# Anonymous tier: what an unauthenticated caller gets when AUTH_ENABLED=false.
#
# "I have no Cognito" and "I want no spend limits" are unrelated statements,
# but one flag used to assert both: auth off meant every caller resolved to
# tier="paid" and quota short-circuited to allow-everything. A deployment can
# be open without being unmetered. Metered against the source IP, since with
# auth off there is no account to bind to.
anon_generate_limit = _safe_int("ANON_GENERATE_LIMIT", 5)
anon_refine_limit = _safe_int("ANON_REFINE_LIMIT", 10)
anon_window_seconds = _safe_int("ANON_WINDOW_SECONDS", 3600)

# Free tier
free_generate_limit = _safe_int("FREE_GENERATE_LIMIT", 1)
free_refine_limit = _safe_int("FREE_REFINE_LIMIT", 2)
free_window_seconds = _safe_int("FREE_WINDOW_SECONDS", 3600)

# Paid tier
paid_daily_limit = _safe_int("PAID_DAILY_LIMIT", 200)
# Paid generation was previously unbounded — the most expensive operation in
# the product (four providers per call) was capped only by the global spend
# ceiling and the per-model caps, both of which are shared across every user,
# so one account could consume the organisation's entire day.
#
# 50 is chosen against the cost table below: ~$0.19 per four-model generation
# is about $9.50/day per paid account, against a $25 global daily ceiling.
# High enough that no legitimate subscriber notices, low enough that a single
# account cannot take the day.
paid_daily_generate_limit = _safe_int("PAID_DAILY_GENERATE_LIMIT", 50)
paid_window_seconds = _safe_int("PAID_WINDOW_SECONDS", 86400)

# ---------------------------------------------------------------------------
# Credit ledger (P0-C: subscription + hard credit allotment).
#
# Credits are stored as integer CENTI-credits (1 credit = 100) so fractional
# action costs — a refine is a quarter of a generate — never need floats in a
# DynamoDB counter.
# ---------------------------------------------------------------------------
credits_per_generate = _safe_int("CREDITS_PER_GENERATE", 100)  # 1.00 credit
credits_per_refine = _safe_int("CREDITS_PER_REFINE", 25)  # 0.25 credit
credits_per_outpaint = _safe_int("CREDITS_PER_OUTPAINT", 25)  # 0.25 credit

# Per-tier monthly allotments, in centi-credits.
free_monthly_credits = _safe_int("FREE_MONTHLY_CREDITS", 500)  # 5 credits
paid_monthly_credits = _safe_int("PAID_MONTHLY_CREDITS", 6500)  # 65 credits

# Free-tier renewal window. PAID tiers renew on Stripe's own subscription
# period boundaries (current_period_end), never on a fixed clock: Stripe's
# monthly cycles run 28-31 days, so a fixed window would hand out credits
# before the customer is billed in some months and leave them short after
# renewal in others.
free_credit_period_seconds = _safe_int("FREE_CREDIT_PERIOD_SECONDS", 2592000)  # 30d

# Fallback renewal window for a paid user whose Stripe period we do not have
# (webhook missed, or subscription predates period persistence). Used only as
# a floor so a paying customer is never left with zero credits.
paid_credit_fallback_period_seconds = _safe_int("PAID_CREDIT_FALLBACK_PERIOD_SECONDS", 2592000)

# Master switch. Off keeps the legacy call-counting quotas, so the ledger can
# be rolled out and rolled back without a redeploy of the old code path.
credits_enabled = os.environ.get("CREDITS_ENABLED", "false").lower() == "true"


# Display prices, in whole cents. These drive the pricing UI via GET /pricing
# rather than VITE_ build vars, so a price experiment is a config change
# instead of a frontend rebuild — and the UI cannot advertise a number the
# backend does not enforce, because there is one source.
paid_price_usd_cents = _safe_int("PAID_PRICE_USD_CENTS", 1900)  # $19/mo
overage_usd_cents_per_credit = _safe_int("OVERAGE_USD_CENTS_PER_CREDIT", 50)


def _require_positive(name: str, value: int) -> int:
    """Reject non-positive ledger values.

    ``_safe_int`` happily accepts 0 and negatives. A zero action cost makes
    that action free, which silently restores the unlimited-generate hole this
    ledger exists to close; a zero or negative allotment or renewal window
    makes the debit arithmetic meaningless. Failing at import is loud and
    immediate — the alternative is a deploy that looks healthy while charging
    nobody.
    """
    if value <= 0:
        raise RuntimeError(
            f"{name} must be a positive integer (got {value}). "
            "A zero or negative value would disable credit enforcement."
        )
    return value


if credits_enabled:
    for _name, _value in (
        ("CREDITS_PER_GENERATE", credits_per_generate),
        ("CREDITS_PER_REFINE", credits_per_refine),
        ("CREDITS_PER_OUTPAINT", credits_per_outpaint),
        ("FREE_MONTHLY_CREDITS", free_monthly_credits),
        ("PAID_MONTHLY_CREDITS", paid_monthly_credits),
        ("FREE_CREDIT_PERIOD_SECONDS", free_credit_period_seconds),
        ("PAID_CREDIT_FALLBACK_PERIOD_SECONDS", paid_credit_fallback_period_seconds),
    ):
        _require_positive(_name, _value)


CREDIT_COSTS: dict[str, int] = {
    "generate": credits_per_generate,
    "refine": credits_per_refine,
    "outpaint": credits_per_outpaint,
}


def credit_cost(endpoint_kind: str) -> int:
    """Credits charged for one call to ``endpoint_kind``, in centi-credits."""
    return CREDIT_COSTS.get(endpoint_kind, 0)


def monthly_credit_allotment(tier: str) -> int:
    """Centi-credits granted per period for ``tier``."""
    if tier == "paid":
        return paid_monthly_credits
    if tier == "free":
        return free_monthly_credits
    return 0


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
    "gemini": 39000,  # $0.039
    "nova": 40000,  # $0.040
    "openai": 40000,  # $0.040
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
# Defaults to $25/day ON, deliberately. Every other guard in this system is
# conditional on AUTH_ENABLED, which defaults false — so a default deploy had
# no spend bound of any kind. This one applies unconditionally and is the last
# thing between a misconfiguration and an unbounded provider bill.
#
# Set to 0 to disable, consciously.
# ---------------------------------------------------------------------------
global_daily_spend_ceiling_usd_micros = _safe_int(
    "GLOBAL_DAILY_SPEND_CEILING_USD_MICROS", 25_000_000
)

# Hard monthly ceiling, in micro-dollars. Default $500/month.
#
# The daily ceiling alone does not bound a month: at $25/day it permits
# roughly $750 across 30 days. This is the number that actually caps the
# invoice while the product is still being figured out.
#
# Deliberately 20x the daily figure, not 30x, so a busy day is not throttled
# for being busy while a single day still cannot consume the month. Set to 0
# to disable, consciously.
monthly_spend_ceiling_usd_micros = _safe_int("MONTHLY_SPEND_CEILING_USD_MICROS", 500_000_000)

# Sub-ceiling for /enhance specifically, in micro-dollars. Default $2/day.
#
# /enhance is unauthenticated, captcha-free and unquota'd (closing that is
# P0-D). Metering it against the shared global budget alone would let anonymous
# traffic exhaust the day's spend and 503 /generate for paying users — turning
# a cost guard into a denial-of-service amplifier. This bounds what the open
# endpoint can consume, independently of the global ceiling it also respects.
#
# Set to 0 to disable this sub-ceiling (the global one still applies).
# $2/day, roughly $60/month, about 12% of the monthly budget. At the previous
# $5 daily figure this unauthenticated endpoint could claim $150/month, 30% of
# the total, which is not a defensible share for a path with no sign-in.
enhance_daily_spend_ceiling_usd_micros = _safe_int(
    "ENHANCE_DAILY_SPEND_CEILING_USD_MICROS", 2_000_000
)

# Circuit breaker over the quota/spend store. See ops/store_breaker.py, which
# carries the reasoning and the residual risk; this is only the tuning.
#
# Every ceiling above reads one DynamoDB table, and every guard that reads it
# fails open, so a partition opens all of them at once and stops the metering
# too. These two numbers are the bound that does not need that table.
#
# Consecutive failures before the breaker trips. Consecutive, not a rate: the
# case being defended against is a partition, which looks like an unbroken
# run. Five is comfortably more than the three or four store calls a single
# /generate makes, so one unlucky request cannot trip it.
store_failure_threshold = _safe_int("STORE_FAILURE_THRESHOLD", 5)

# Generations a tripped container may still dispatch before it sheds.
#
# 20 at roughly $0.19 per four-model generation is about $3.80 per container.
# With ReservedConcurrentExecutions: 10 the fleet-wide worst case is about
# $38, against a $25 daily and $500 monthly ceiling. Deliberately above the
# daily ceiling: this is a backstop for the case where the ceilings cannot be
# evaluated at all, not a second ceiling, and it should never bind while
# DynamoDB is healthy.
degraded_dispatch_budget = _safe_int("DEGRADED_DISPATCH_BUDGET", 20)

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

# API Gateway HTTP APIs cap the integration timeout at 30 seconds and the
# quota is not adjustable. One second of margin is kept so a request that
# is going to be abandoned is abandoned by us, with a logged reason,
# rather than by the gateway with a 504 and no record.
#
# Declared first because two budgets below are derived from it.
gateway_integration_timeout_seconds = 29

api_client_timeout = _safe_float("API_CLIENT_TIMEOUT", 60.0)

# Every provider must bound its own call below this, because the dispatch
# timeout in run_generation cannot cancel a future that has already started:
# the call is blocking I/O inside a worker thread. If a provider outlives the
# budget the dispatch is abandoned, the session records the model as failed,
# and the provider generates and bills for the image anyway.
#
# 70s is legitimate only because the dispatch no longer runs inside the HTTP
# request: with GENERATE_ASYNC=true it runs in a worker invocation that has the
# function's 900s timeout and no gateway in front of it. Synchronous mode has
# no such headroom -- see sync_mode_fits_gateway below.
generate_dispatch_budget_seconds = api_client_timeout + 10

# /iterate, /outpaint and /enhance are answered inside the HTTP request, so
# their whole call chain has to fit under the gateway ceiling rather than the
# dispatch budget above -- there is no worker invocation behind them. Four
# seconds are reserved for validation, quota, the session read/write and
# response assembly.
sync_dispatch_budget_seconds = float(gateway_integration_timeout_seconds - 4)

image_download_timeout = _safe_int("IMAGE_DOWNLOAD_TIMEOUT", 30)

# Clamped rather than merely defaulted. A 30s enhance timeout inside a 29s
# gateway ceiling cannot succeed at its limit: the gateway returns 504 first,
# the caller is told the request failed, and the LLM call is billed anyway.
# ADR-A12 records why /enhance is not gated in other ways.
enhance_timeout = min(_safe_float("ENHANCE_TIMEOUT", 30.0), sync_dispatch_budget_seconds)
generate_thread_workers = _safe_int("GENERATE_THREAD_WORKERS", 4)

# When true (the default), POST /generate answers the caller as soon as the
# session exists and hands the provider dispatch to an asynchronous
# self-invocation. When false, the handler runs the generation inline and
# returns the full result -- the pre-async behaviour, and the only mode that
# works where there is no Lambda service to invoke: `sam local start-api` and
# the MiniStack E2E suite.
generate_async = os.environ.get("GENERATE_ASYNC", "true").lower() == "true"


def sync_mode_fits_gateway(budget_seconds: float) -> bool:
    """Whether a synchronous dispatch budget clears the gateway ceiling.

    Deliberately NOT called at import. GENERATE_ASYNC=false exists for the
    environments that have no gateway at all, so failing closed there would
    enforce a constraint that does not apply and would break the escape hatch.
    It is also unsatisfiable in a deployed stack: API_CLIENT_TIMEOUT is neither
    a SAM parameter nor a Lambda environment variable, so a deployment always
    gets the 60.0 default and a budget of 70. The relationship is asserted by
    tests/backend/unit/test_dispatch_budget.py instead. See ADR-A1.
    """
    return budget_seconds <= gateway_integration_timeout_seconds
