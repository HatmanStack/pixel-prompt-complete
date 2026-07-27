"""
Main Lambda handler for Pixel Prompt v2.
Routes API requests to appropriate handlers for image generation,
iteration, outpainting, and session status.
"""

import base64
import json
import os
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import boto3
from botocore.config import Config as BotoConfig

import config
from api.enhance import PromptEnhancer
from api.log import handle_log
from api.pricing import handle_pricing
from auth.claims import extract_admin_groups
from auth.guest_token import get_guest_token_service
from config import (
    ITERATION_WARNING_THRESHOLD,
    MAX_ITERATIONS,
    MODELS,
    cloudfront_domain,
    cors_allowed_origin,
    generate_thread_workers,
    get_enabled_models,
    get_model,
    get_model_config_dict,
    s3_bucket,
)
from jobs.manager import SessionManager
from models.context import ContextManager, create_context_entry
from models.providers import (
    get_handler,
    get_iterate_handler,
    get_outpaint_handler,
    sanitize_error_message,
)
from ops.cost_meter import CostMeter
from ops.metrics import emit_quota_rejection, emit_request_metric
from ops.model_counters import ModelCounterService
from prompts.repository import PromptHistoryRepository
from users.quota import QuotaResult, enforce_quota
from users.repository import UserRepository
from users.tier import TierContext, anon_tier, persist_guest, resolve_tier
from utils import error_responses
from utils.content_filter import ContentFilter
from utils.logger import StructuredLogger
from utils.storage import ImageStorage

# Type aliases for Lambda events and responses
LambdaEvent = dict[str, Any]
LambdaContext = Any  # AWS Lambda context object
ApiResponse = dict[str, Any]

# Request body size limits
MAX_BODY_SIZE = 1_048_576  # 1 MB for generation endpoints
MAX_LOG_BODY_SIZE = 10_240  # 10 KB for log endpoint

# Reserved metadata keys that must not be overwritten by client log payloads
_RESERVED_LOG_METADATA_KEYS = frozenset(
    {
        "timestamp",
        "level",
        "correlation_id",
        "message",
    }
)

# Initialize components at module level (Lambda container reuse)
s3_client = boto3.client("s3")

# Session manager (replaces job manager)
session_manager = SessionManager(s3_client, s3_bucket)

# Context manager for iteration history
context_manager = ContextManager(s3_client, s3_bucket)

# Image storage
image_storage = ImageStorage(s3_client, s3_bucket, cloudfront_domain)

# User repository (DynamoDB) and guest token service.
# Safe to construct when AUTH_ENABLED=false; neither is touched in that case
# because resolve_tier() / enforce_quota() short-circuit.
_user_repo = UserRepository(config.users_table_name)
_guest_service = get_guest_token_service() if config.guest_token_secret else None

# Per-model cost ceiling service
_model_counter_service = ModelCounterService(_user_repo)
_cost_meter = CostMeter(_user_repo)

# Prompt history repository
_prompt_history = PromptHistoryRepository(config.users_table_name)

# Content filter
content_filter = ContentFilter()

# Prompt enhancer
prompt_enhancer = PromptEnhancer()

# Module-level thread pools for Lambda container reuse.
# Separate pools prevent gallery metadata fetches from starving generation threads.
_executor = ThreadPoolExecutor(max_workers=generate_thread_workers)
_gallery_executor = ThreadPoolExecutor(max_workers=4)

# Lambda client for the asynchronous /generate self-invoke. Lazily built so a
# unit test without moto never constructs one at import.
_lambda_client = None

# The Invoke that hands work to the worker is itself on the request path, so it
# is bounded for the same reason the CloudWatch client is (ops/metrics.py): an
# unbounded call would put the request back inside the gateway ceiling it
# exists to escape. Two attempts, not more -- a retried Event invocation that
# both attempts deliver would generate the images twice.
_INVOKE_CONNECT_TIMEOUT_SECONDS = 2
_INVOKE_READ_TIMEOUT_SECONDS = 5
_INVOKE_MAX_ATTEMPTS = 2


def _get_lambda_client():
    """Return a lazily-initialized Lambda client with bounded timeouts."""
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client(
            "lambda",
            config=BotoConfig(
                connect_timeout=_INVOKE_CONNECT_TIMEOUT_SECONDS,
                read_timeout=_INVOKE_READ_TIMEOUT_SECONDS,
                retries={"mode": "standard", "total_max_attempts": _INVOKE_MAX_ATTEMPTS},
            ),
        )
    return _lambda_client


@dataclass
class ValidatedRequest:
    """Result of successful request validation."""

    body: dict[str, Any]
    ip: str
    prompt: str
    tier: TierContext | None = None


def _daily_spend_exceeded(now: int | None = None) -> bool:
    """True when today's metered spend has reached the configured ceiling.

    Fails OPEN on a read error: if the spend accumulator is unreadable we
    cannot prove the budget is blown, and hard-failing every billable request
    on a transient DynamoDB blip would be a self-inflicted outage. The read
    error is logged so the gap is visible.

    This is check-then-act, not an atomic reservation: the spend write happens
    after the provider call, so concurrent requests can all read an
    under-ceiling total and all proceed. The overshoot is bounded by Lambda's
    reserved concurrency (10), i.e. ~10 requests' worth. At current cost-table
    values a four-model /generate plus its prompt adaptation is ~196,000
    micros, so the worst case is ~$2 against the $25 default ceiling — still
    single-digit dollars, but ~8% of the ceiling rather than the ~2% it was
    under the four-times-larger ceiling this paragraph originally assumed.
    That is a deliberately weaker guarantee than the per-model cap, which
    reserves atomically via a conditional UpdateItem. The "tightened toward
    the overshoot size" trigger below has already fired once; revisit again if
    concurrency is raised substantially or the ceiling is tightened further.
    """
    ceiling = config.global_daily_spend_ceiling_usd_micros
    if ceiling <= 0:
        return False
    try:
        spend = _cost_meter.get_daily_spend(now=now)
    except Exception as e:
        StructuredLogger.error(f"Spend ceiling check failed, allowing request: {e}")
        return False
    return int(spend.get("totalMicros", 0)) >= ceiling


def _monthly_spend_exceeded(now: int | None = None) -> bool:
    """True when this calendar month's spend has reached the ceiling.

    The daily ceiling bounds a bad day; this bounds a bad month. Without it,
    sustained traffic at just under the daily limit runs to roughly 30x it.

    Fails open on a read error for the same reason as the daily check: an
    unreadable counter is not evidence the budget is blown.
    """
    ceiling = config.monthly_spend_ceiling_usd_micros
    if ceiling <= 0:
        return False
    try:
        spend = _cost_meter.get_monthly_spend(now=now)
    except Exception as e:
        StructuredLogger.error(f"Monthly ceiling check failed, allowing request: {e}")
        return False
    return int(spend.get("totalMicros", 0)) >= ceiling


def _enhance_spend_exceeded(now: int | None = None) -> bool:
    """True when /enhance has used up its own sub-budget.

    /enhance is unauthenticated and unquota'd, so without a dedicated bound it
    could burn the whole global budget and make /generate return 503 for paying
    users — a cost guard doubling as a denial-of-service amplifier. Fails open
    on a read error for the same reason as the global check.
    """
    ceiling = config.enhance_daily_spend_ceiling_usd_micros
    if ceiling <= 0:
        return False
    try:
        spend = _cost_meter.get_daily_spend(now=now)
    except Exception as e:
        StructuredLogger.error(f"Enhance ceiling check failed, allowing request: {e}")
        return False
    return int(spend.get("enhanceMicros", 0)) >= ceiling


def _spend_ceiling_exceeded(endpoint_kind: str) -> tuple[bool, str]:
    """Evaluate every ceiling that applies to ``endpoint_kind``.

    Returns (exceeded, scope_label_for_logging).
    """
    # Monthly first: it is the bound that actually caps the invoice, and a
    # breach of it should not be reported as a daily problem.
    if _monthly_spend_exceeded():
        return True, "Monthly"
    if _daily_spend_exceeded():
        return True, "Global"
    if endpoint_kind == "enhance" and _enhance_spend_exceeded():
        return True, "Enhance"
    return False, ""


def _enforce_age_gate(tier_ctx: TierContext, body: dict[str, Any]) -> ApiResponse | None:
    """Require an 18+ affirmation before a first generation.

    Returns an error response to send, or None to proceed.

    A prior affirmation is remembered against the caller's identity so the
    prompt appears once rather than on every generation. If the store is
    unreachable we ask again rather than either blocking the request or waving
    it through: being unable to recall that someone answered is a reason to
    repeat the question, and the degraded state is a re-prompt rather than an
    outage. The subsequent write is best effort for the same reason.
    """
    if _user_repo is None:
        return None

    identity = tier_ctx.user_id
    affirmed_now = body.get("ageAffirmed") is True

    if not affirmed_now:
        try:
            if _user_repo.has_affirmed_age(identity):
                return None
        except Exception as e:
            StructuredLogger.error(f"Age affirmation lookup failed, re-prompting: {e}")
        return response(403, error_responses.age_verification_required())

    now = int(time.time())
    # Guest and anonymous identities are ephemeral counter buckets, so their
    # record carries a TTL matching the quota window the same identity is
    # metered against. Real accounts get None: a TTL there deletes a customer.
    if tier_ctx.tier == "guest":
        window = config.guest_window_seconds
    elif tier_ctx.tier == "anon":
        window = config.anon_window_seconds
    else:
        window = None
    try:
        _user_repo.record_age_affirmation(identity, now, window)
    except Exception as e:
        # The caller answered; failing to persist it costs a repeat prompt on
        # their next generation, not access now.
        StructuredLogger.error(f"Failed to record age affirmation: {e}")
    return None


def _enforce_quota_safe(tier_ctx: TierContext, endpoint_kind: str, now: int) -> "QuotaResult":
    """Enforce quota, failing OPEN if the quota store is unreachable.

    Applied to every tier, not just anon. The anon path had its own
    try/except while guest, free and paid propagated straight to the
    top-level handler and returned 500 — so a DynamoDB blip took the service
    down for exactly the users who are paying for it, which is the opposite
    of the intended behaviour.

    Fail-open is bounded: the global daily spend ceiling still applies and is
    checked before this. The residual risk is that a *persistent* store
    failure means silently unmetered traffic, which is why this logs at
    ERROR rather than WARNING — it needs to be alarmable.
    """
    try:
        return enforce_quota(tier_ctx, endpoint_kind, _user_repo, now)
    except Exception as e:
        StructuredLogger.error(
            f"Quota check failed, allowing request: {e}",
            tier=tier_ctx.tier,
            endpoint=endpoint_kind,
        )
        from users.quota import QuotaResult

        return QuotaResult(allowed=True, reason=None, reset_at=0, usage={})


def _model_runtime_disabled(model_name: str, correlation_id: str | None = None) -> bool:
    """True when an admin has disabled ``model_name`` at runtime.

    The single reader of ``config#model#<name>``. It exists as a helper rather
    than an inline call because the read had exactly one caller — the
    ``/generate`` dispatch filter — so a model switched off for burning money
    or hallucinating went on serving every ``/iterate`` and ``/outpaint``
    request. Three paths asking one function is what stops a fourth from
    diverging.

    Fails OPEN on a store error, consistent with every other guard that reads
    this table (quota, per-model caps, spend ceilings): an unreachable config
    store is not evidence a model is disabled, and refusing all refinement
    because DynamoDB hiccuped would be a self-inflicted outage. Logged at
    ERROR so a persistent failure — which means a kill switch that no longer
    kills — is alarmable.
    """
    try:
        runtime_cfg = _user_repo.get_model_runtime_config(model_name)
    except Exception as e:
        StructuredLogger.error(
            f"Runtime model config check failed, allowing {model_name}: {e}",
            correlation_id=correlation_id,
        )
        return False
    return bool(runtime_cfg and runtime_cfg.get("disabled"))


def _seconds_until_reset(reset_at: int, now: int) -> int | None:
    """Seconds a rejected caller must wait for their window to reset.

    Returns None when the quota layer reported no usable reset instant — the
    fail-open path returns ``reset_at=0``, and a stale one is already past.
    A caller is better served by no Retry-After than by an invented interval
    it would obey.
    """
    if reset_at <= now:
        return None
    return reset_at - now


# Which counter ``enforce_quota`` incremented, per (tier, endpoint). Mirrors
# users/quota.py; the third element names the config attribute holding that
# bucket's window length, read at call time so a reloaded config is honoured.
#
# ``guest`` is absent DELIBERATELY, not by omission. A guest identity is
# honour-system — dropping the cookie mints a new one, which is exactly why
# users/quota.py meters guests against their source IP as well — so refunding
# a guest is an unlimited retry for anyone who wants one.
_REFUND_COUNTERS: dict[tuple[str, str], tuple[str, str, str]] = {
    ("free", "generate"): ("generateCount", "windowStart", "free_window_seconds"),
    ("free", "refine"): ("refineCount", "windowStart", "free_window_seconds"),
    ("free", "outpaint"): ("refineCount", "windowStart", "free_window_seconds"),
    ("paid", "generate"): ("dailyGenerateCount", "dailyResetAt", "paid_window_seconds"),
    ("paid", "refine"): ("dailyCount", "dailyResetAt", "paid_window_seconds"),
    ("paid", "outpaint"): ("dailyCount", "dailyResetAt", "paid_window_seconds"),
    ("anon", "generate"): ("generateCount", "windowStart", "anon_window_seconds"),
    ("anon", "refine"): ("refineCount", "windowStart", "anon_window_seconds"),
    ("anon", "outpaint"): ("refineCount", "windowStart", "anon_window_seconds"),
}


def _refund_usage(
    tier_ctx: TierContext | None, endpoint_kind: str, correlation_id: str | None = None
) -> None:
    """Return what a request consumed when it produced nothing.

    There are two quota systems and this has to serve both. With
    ``CREDITS_ENABLED`` the charge is a credit debit; without it — the shipped
    default — ``enforce_quota`` consumes the tier's call counter *as* the
    check, so that counter is what a failed request has to give back. Refunding
    only the ledger meant the entire mechanism was inert in a default deploy,
    and a free user with ``FREE_GENERATE_LIMIT=1`` lost their hour to a
    provider outage with no recourse.

    Credits are debited before dispatch, which is required: reserving after
    the provider call would let concurrent requests overdraw. The consequence
    is that a request charged up front but yielding no image has taken the
    user's money for nothing — worst on /generate, the most expensive action
    in the ledger. The call counter has the same shape and the same problem.

    Refunding only on TOTAL failure is deliberate. A partial result is still a
    result: the product's premise is comparing models, and pro-rating would
    need per-model pricing the ledger does not have.

    Best-effort — a failed refund is logged, never raised, because the caller
    is already on an error path and a second failure there would replace a
    bad result with no result.

    INVARIANT: every path that returns non-2xx after quota enforcement must
    call this exactly once. The early-exit paths (no models enabled, every
    model capped, model disabled at runtime, bad session reference, missing
    source image) are the easiest to miss precisely because they never reach a
    provider — no cost was incurred, so charging for them is the least
    defensible case of all.
    """
    if tier_ctx is None:
        return

    if config.credits_enabled:
        if tier_ctx.tier not in ("free", "paid"):
            return
        amount = config.credit_cost(endpoint_kind)
        if amount <= 0:
            return
        try:
            _user_repo.grant_credits(tier_ctx.user_id, amount)
            StructuredLogger.info(
                f"Refunded {amount} centi-credits for a failed {endpoint_kind}",
                correlation_id=correlation_id,
                userId=tier_ctx.user_id,
            )
        except Exception as e:
            StructuredLogger.error(
                f"Failed to refund credits for {endpoint_kind}: {e}",
                correlation_id=correlation_id,
                userId=tier_ctx.user_id,
            )
        return

    mapping = _REFUND_COUNTERS.get((tier_ctx.tier, endpoint_kind))
    if mapping is None:
        return
    counter, window_field, window_attr = mapping
    try:
        refunded = _user_repo.decrement_counter(
            tier_ctx.user_id,
            counter,
            window_field,
            getattr(config, window_attr),
            int(time.time()),
        )
        if refunded:
            StructuredLogger.info(
                f"Refunded one {counter} for a failed {endpoint_kind}",
                correlation_id=correlation_id,
                userId=tier_ctx.user_id,
            )
    except Exception as e:
        StructuredLogger.error(
            f"Failed to refund {counter} for {endpoint_kind}: {e}",
            correlation_id=correlation_id,
            userId=tier_ctx.user_id,
        )


def _parse_and_validate_request(
    event: LambdaEvent,
    require_prompt: bool = True,
    default_prompt: str = "",
    max_body_size: int = MAX_BODY_SIZE,
    max_prompt_length: int = 1000,
    endpoint_kind: str = "none",
) -> tuple[ValidatedRequest | None, ApiResponse | None]:
    """Shared request validation for POST handlers.

    Performs: body size check, JSON parsing, IP extraction, tier resolution,
    quota enforcement, prompt validation, and content filtering.

    ``endpoint_kind`` is one of ``"generate"``, ``"refine"``, ``"outpaint"``,
    ``"enhance"`` or ``"none"``
    (skip quota enforcement).

    Returns:
        (ValidatedRequest, None) on success, or (None, error_response) on failure.
    """
    raw_body = event.get("body", "")
    if len(raw_body) > max_body_size:
        return None, response(413, {"error": "Request body too large"})

    try:
        body = json.loads(raw_body or "{}")
    except json.JSONDecodeError:
        return None, response(400, error_responses.invalid_json())

    # Spend ceilings, checked first. Deliberately NOT gated on auth_enabled:
    # every other cost guard is, which is exactly why a default deploy had no
    # spend bound at all. Placed before tier resolution, CAPTCHA (an external
    # HTTP call) and content filtering because the check depends on none of
    # them, and a ceiling breach is precisely when rejecting cheaply matters.
    if endpoint_kind in ("generate", "refine", "outpaint", "enhance"):
        exceeded, scope = _spend_ceiling_exceeded(endpoint_kind)
        if exceeded:
            StructuredLogger.error(
                f"{scope} spend ceiling reached, rejecting billable request",
                endpoint=endpoint_kind,
            )
            return None, response(503, error_responses.daily_spend_ceiling())

    # Prefer real client IP from API Gateway, fall back to body.ip for local dev
    ip = event.get("requestContext", {}).get("http", {}).get("sourceIp") or body.get(
        "ip", "unknown"
    )

    # Tier resolution
    if config.auth_enabled:
        if _guest_service is None:
            return None, response(
                500,
                {
                    "error": "Server misconfigured: GUEST_TOKEN_SECRET is required when AUTH_ENABLED=true"
                },
            )
        tier_ctx = resolve_tier(event, _user_repo, _guest_service)
    else:
        tier_ctx = anon_tier(event)

    # CAPTCHA verification for guest /generate requests
    if config.captcha_enabled and tier_ctx.tier == "guest" and endpoint_kind == "generate":
        captcha_token = body.get("captchaToken")
        if not captcha_token:
            return None, response(403, error_responses.captcha_required())
        from ops.captcha import verify_turnstile

        if not verify_turnstile(captcha_token, ip):
            return None, response(403, error_responses.captcha_failed())

    # Guests cannot refine at all, so reject before writing anything. Checked
    # here rather than with the other quota logic below because a request that
    # can never succeed must not create a record on its way to being refused.
    if tier_ctx.tier == "guest" and endpoint_kind in ("refine", "outpaint"):
        return None, response(402, error_responses.auth_required())

    # Guest record is written only now: identify -> verify -> persist. Writing
    # in resolve_tier let a caller who cannot solve the CAPTCHA still create a
    # DynamoDB item on every request.
    if tier_ctx.guest_row_pending:
        persist_guest(tier_ctx, _user_repo)

    # Extract prompt
    prompt = body.get("prompt", default_prompt)

    if require_prompt:
        if not prompt:
            return None, response(400, error_responses.prompt_required())
        if len(prompt) > max_prompt_length:
            return None, response(
                400, error_responses.prompt_too_long(max_length=max_prompt_length)
            )

    # Content filter
    if prompt and content_filter.check_prompt(prompt):
        return None, response(400, error_responses.inappropriate_content())

    # Age gate. Google's API terms allow use only where the calling service is
    # not "likely to be accessed by" individuals under 18, which is a stricter
    # test than a checkbox and is not satisfied by a public URL that asks
    # nothing. Enforced on /generate only: refinement requires an existing
    # session, which required a generate, which required this.
    #
    # Placed here for the same reason quota is: a malformed request should fail
    # local validation cheaply rather than costing a DynamoDB read and coming
    # back as 403 when the real problem was a missing prompt. Before quota, so
    # a request we are about to refuse does not consume any.
    if config.age_gate_enabled and endpoint_kind == "generate":
        err = _enforce_age_gate(tier_ctx, body)
        if err:
            return None, err

    # Quota enforcement (after validation so invalid requests don't consume quota)
    if endpoint_kind in ("generate", "refine", "outpaint"):
        # (Guest refine/outpaint was already refused above, before any write.)
        now = int(time.time())
        result = _enforce_quota_safe(tier_ctx, endpoint_kind, now)
        if not result.allowed:
            # A user hitting a wall and an attacker probing one used to look
            # identical from outside, and a limit set wrongly low produced
            # silent churn instead of a signal.
            emit_quota_rejection(tier_ctx.tier, endpoint_kind, result.reason or "unknown")
            # Every rolling-window rejection knows when it lifts. Passing it
            # down is what puts a Retry-After on the wire: error_response only
            # writes the field when it is given one, so these 429s carried no
            # backoff hint at all and a client had nothing to act on.
            retry_after = _seconds_until_reset(result.reset_at, now)
            if result.reason == "suspended":
                return None, response(403, error_responses.account_suspended())
            if result.reason == "guest_ip":
                return None, response(429, error_responses.guest_ip_limit(retry_after=retry_after))
            if result.reason == "guest_global":
                return None, response(
                    429, error_responses.guest_global_limit(retry_after=retry_after)
                )
            if result.reason == "insufficient_credits":
                return None, response(
                    402,
                    error_responses.insufficient_credits(
                        tier_ctx.tier,
                        result.reset_at,
                        remaining=result.usage.get("creditsRemaining", 0),
                        required=config.credit_cost(endpoint_kind),
                    ),
                )
            return None, response(
                429,
                error_responses.tier_quota_exceeded(
                    tier_ctx.tier, result.reset_at, retry_after=retry_after
                ),
            )

    return ValidatedRequest(body=body, ip=ip, prompt=prompt, tier=tier_ctx), None


def _handle_successful_result(
    session_id: str,
    model_name: str,
    prompt: str,
    result: dict[str, Any],
    iteration_index: int,
    target: str,
    duration: float,
    visibility: str,
    context_prompt: str | None = None,
) -> dict[str, Any]:
    """Handle a successful handler result: upload, complete iteration, add context.

    Args:
        context_prompt: Prompt string to store in context. Defaults to ``prompt``.
        visibility: ``"private"`` routes the image to a prefix with no unsigned
            URL. Deliberately has no default: defaulting to public would mean a
            call site nobody remembered to update publishes a paid user's image,
            and defaulting to private would quietly break the gallery. Required
            means a missed call site is a TypeError.

    Returns:
        Dict with image_key and image_url.
    """
    image_key = image_storage.upload_image(
        result["image"],
        target,
        model_name,
        iteration=iteration_index,
        session_id=session_id,
        visibility=visibility,
    )

    session_manager.complete_iteration(
        session_id,
        model_name,
        iteration_index,
        image_key,
        duration,
    )

    entry = create_context_entry(iteration_index, context_prompt or prompt, image_key)
    context_manager.add_entry(session_id, model_name, entry)

    return {
        "image_key": image_key,
        "image_url": image_storage.get_cloudfront_url(image_key),
    }


def _handle_failed_result(
    session_id: str,
    model_name: str,
    iteration_index: int,
    error_msg: str,
) -> None:
    """Handle a failed handler result: mark iteration as failed."""
    session_manager.fail_iteration(session_id, model_name, iteration_index, error_msg)


def extract_correlation_id(event: LambdaEvent) -> str:
    """Extract correlation ID from event headers or generate new one."""
    headers = event.get("headers", {}) or {}
    correlation_id = headers.get("x-correlation-id") or headers.get("X-Correlation-ID")
    return correlation_id or str(uuid4())


def _route_admin(path: str, method: str, event: LambdaEvent, correlation_id: str) -> ApiResponse:
    """Dispatch admin API routes.

    All ``/admin/*`` paths are routed through this function.
    Each handler performs its own admin auth check.
    """
    from admin.metrics import handle_admin_metrics, handle_admin_revenue
    from admin.models import (
        handle_admin_model_disable,
        handle_admin_model_enable,
        handle_admin_models_list,
    )
    from admin.users import (
        handle_admin_notify,
        handle_admin_suspend,
        handle_admin_unsuspend,
        handle_admin_user_detail,
        handle_admin_users_list,
    )

    parts = path.strip("/").split("/")
    # parts[0] == "admin", parts[1] == resource, ...

    if len(parts) < 2:
        return response(404, {"error": "Not found", "path": path})

    resource = parts[1]

    if resource == "users":
        if len(parts) == 2 and method == "GET":
            return handle_admin_users_list(event, _user_repo, correlation_id)
        if len(parts) == 3 and method == "GET":
            return handle_admin_user_detail(event, _user_repo, correlation_id)
        if len(parts) == 4:
            action = parts[3]
            if action == "suspend" and method == "POST":
                return handle_admin_suspend(event, _user_repo, correlation_id)
            if action == "unsuspend" and method == "POST":
                return handle_admin_unsuspend(event, _user_repo, correlation_id)
            if action == "notify" and method == "POST":
                return handle_admin_notify(event, _user_repo, correlation_id)

    elif resource == "models":
        if len(parts) == 2 and method == "GET":
            return handle_admin_models_list(event, _model_counter_service, correlation_id)
        if len(parts) == 4:
            action = parts[3]
            if action == "disable" and method == "POST":
                return handle_admin_model_disable(event, _user_repo, correlation_id)
            if action == "enable" and method == "POST":
                return handle_admin_model_enable(event, _user_repo, correlation_id)

    elif resource == "metrics" and len(parts) == 2 and method == "GET":
        return handle_admin_metrics(event, _user_repo, _model_counter_service, correlation_id)

    elif resource == "revenue" and len(parts) == 2 and method == "GET":
        return handle_admin_revenue(event, _user_repo, correlation_id)

    return response(404, {"error": "Not found", "path": path})


def lambda_handler(event: LambdaEvent, context: LambdaContext) -> ApiResponse:
    """Main Lambda handler function."""
    # Handle scheduled events (EventBridge)
    if event.get("source") == "scheduled" and event.get("action") == "daily_snapshot":
        from ops.metrics import handle_daily_snapshot

        return handle_daily_snapshot(event, context, repo=_user_repo)

    # Asynchronous /generate worker. Must come before extract_correlation_id
    # and the path parsing below, both of which assume an HTTP event.
    if event.get("source") == "generate_worker":
        try:
            run_generation(event)
        except Exception as e:
            # Deliberately not re-raised. Every per-model failure is already
            # recorded on the session, so raising would add an unexplained
            # invocation error -- and a platform-chosen retry that would
            # generate and bill the images a second time -- on top of a session
            # the client can already read the truth from.
            StructuredLogger.error(
                f"Generate worker failed: {e}",
                correlation_id=event.get("correlationId"),
                sessionId=event.get("sessionId"),
                traceback=traceback.format_exc(),
            )
        return {"statusCode": 200}

    correlation_id = extract_correlation_id(event)

    path = event.get("rawPath", event.get("path", ""))
    # Remove known stage prefixes (e.g. /Prod/generate -> /generate)
    for stage_prefix in ("/Prod/", "/Staging/", "/Dev/"):
        if path.startswith(stage_prefix):
            path = path[len(stage_prefix) :]
            break
    # Ensure path starts with /
    if path and not path.startswith("/"):
        path = "/" + path

    method = (
        event.get("requestContext", {}).get("http", {}).get("method", event.get("httpMethod", ""))
    )

    StructuredLogger.info(f"Request: {method} {path}", correlation_id=correlation_id)

    if method == "OPTIONS":
        return response(200, {"message": "CORS preflight"})

    try:
        # Route based on path and method
        if path == "/generate" and method == "POST":
            return handle_generate(event, correlation_id)
        elif path == "/iterate" and method == "POST":
            return handle_iterate(event, correlation_id)
        elif path == "/outpaint" and method == "POST":
            return handle_outpaint(event, correlation_id)
        elif path.startswith("/status/") and method == "GET":
            return handle_status(event, correlation_id)
        elif path.startswith("/download/") and method == "GET":
            return handle_download(event, correlation_id)
        elif path == "/enhance" and method == "POST":
            return handle_enhance(event, correlation_id)
        elif path == "/log" and method == "POST":
            return handle_log_endpoint(event)
        elif path == "/pricing" and method == "GET":
            return handle_pricing(event, correlation_id)
        elif path == "/gallery/list" and method == "GET":
            return handle_gallery_list(event, correlation_id)
        elif path.startswith("/gallery/") and method == "GET":
            return handle_gallery_detail(event, correlation_id)
        elif path == "/prompts/recent" and method == "GET":
            return handle_prompts_recent(event, correlation_id)
        elif path == "/prompts/history" and method == "GET":
            return handle_prompts_history(event, correlation_id)
        elif path == "/me" and method == "GET":
            return handle_me(event, correlation_id)
        elif path == "/billing/checkout" and method == "POST":
            from billing.checkout import handle_billing_checkout

            return handle_billing_checkout(event, _user_repo, correlation_id)
        elif path == "/billing/portal" and method == "POST":
            from billing.portal import handle_billing_portal

            return handle_billing_portal(event, _user_repo, correlation_id)
        elif path == "/stripe/webhook" and method == "POST":
            from billing.webhook import handle_stripe_webhook

            return handle_stripe_webhook(event, _user_repo, correlation_id)
        elif path.startswith("/admin/"):
            return _route_admin(path, method, event, correlation_id)
        else:
            return response(404, {"error": "Not found", "path": path, "method": method})

    except Exception as e:
        StructuredLogger.error(
            f"Error in lambda_handler: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, {"error": "Internal server error"})


def _dispatch_generation_async(payload: dict[str, Any], correlation_id: str | None = None) -> bool:
    """Hand the provider dispatch to a worker invocation. True when accepted.

    Returns False on ANY failure -- AWS_LAMBDA_FUNCTION_NAME absent, the
    lambda:InvokeFunction grant missing, the account throttling -- and the
    caller then runs the dispatch inline.

    That fallback is load-bearing. A deploy whose IAM grant did not land
    degrades to the pre-async behaviour (a slow request that may 504) rather
    than to sessions that are created, answered 202, and never worked on.
    AWS_LAMBDA_FUNCTION_NAME is set by the Lambda runtime; outside Lambda it is
    absent, which is exactly when falling back is right.
    """
    try:
        function_name = os.environ["AWS_LAMBDA_FUNCTION_NAME"]
        _get_lambda_client().invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps(payload).encode(),
        )
        return True
    except Exception as e:
        StructuredLogger.error(
            f"Async generate dispatch failed, running inline instead: {e}",
            correlation_id=correlation_id,
            sessionId=payload.get("sessionId"),
        )
        return False


def run_generation(payload: dict[str, Any]) -> dict[str, Any]:
    """Perform the provider dispatch for an already-created session.

    Called synchronously by handle_generate when GENERATE_ASYNC is false,
    and by the asynchronous worker branch of lambda_handler otherwise.
    Everything that must happen before the caller is answered -- spend
    ceilings, tier, CAPTCHA, age gate, quota, per-model slot reservation,
    session creation -- has already happened by the time this runs.

    `payload` carries only JSON-serialisable values because in async mode it
    crosses an Invoke boundary. Returns the per-model results map, including
    the skipped entries the request path computed, so synchronous mode can
    return it to the caller verbatim.
    """
    session_id: str = payload["sessionId"]
    prompt: str = payload["prompt"]
    model_names: list[str] = payload["modelNames"]
    skipped_models: dict[str, Any] = payload.get("skipped") or {}
    visibility: str = payload["visibility"]
    correlation_id: str | None = payload.get("correlationId")

    # A MINIMAL TierContext, not a real identity. Only two fields are
    # load-bearing here: `_refund_usage` reads `.tier` and `.user_id`, and
    # `_cost_meter.record_models` reads the same two. Everything else is
    # filler and must never be used for an authorization decision -- in
    # particular `is_authenticated=False` is a placeholder, not a claim about
    # the caller, who was already authenticated in the request path.
    # None when the request had no tier context at all, which both consumers
    # already handle.
    tier_ctx: TierContext | None = None
    if payload.get("tier") is not None:
        tier_ctx = TierContext(
            tier=payload["tier"],
            user_id=payload.get("userId") or "",
            email=None,
            is_authenticated=False,
            guest_token_id=None,
            issue_guest_cookie=False,
        )

    results: dict[str, Any] = {}

    # Resolved from get_enabled_models(), not config.get_model(): the request
    # path picked these names out of exactly that list, so this is the same
    # source of truth. config.get_model raises ValueError for a model that is
    # not enabled, which would abandon the whole dispatch over one model.
    #
    # A name can only fail to resolve here if the worker container's
    # configuration differs from the request container's -- a deploy that
    # changes a *_ENABLED variable while requests are in flight. That was
    # impossible before this refactor, because the ModelConfig objects were
    # carried in memory rather than rebuilt from a name. It becomes possible
    # the moment the dispatch can cross an invocation boundary, so the model
    # is marked failed on the session: leaving its column pending would strand
    # the session short of a terminal status and the client would poll until
    # it gave up.
    enabled_by_name = {m.name: m for m in get_enabled_models()}
    models_to_dispatch = [enabled_by_name[name] for name in model_names if name in enabled_by_name]
    for _missing in [name for name in model_names if name not in enabled_by_name]:
        StructuredLogger.error(
            "Model was reserved for dispatch but is not enabled in this container",
            correlation_id=correlation_id,
            sessionId=session_id,
            model=_missing,
        )
        results[_missing] = {"status": "error", "error": "Model is not enabled"}
        try:
            _handle_failed_result(
                session_id,
                _missing,
                session_manager.add_iteration(session_id, _missing, prompt),
                "Model is not enabled",
            )
        except Exception as e:
            StructuredLogger.warning(
                f"Could not mark unresolved model as failed: {e}",
                correlation_id=correlation_id,
                sessionId=session_id,
                model=_missing,
            )

    # Adapt prompt per model (single LLM call, ~4x cheaper than per-model calls)
    adapted_prompts = prompt_enhancer.adapt_per_model(
        prompt, model_names, correlation_id=correlation_id
    )

    # Re-filter the rewritten prompts. The user's prompt was checked at
    # validation, but what actually reaches the provider is this LLM
    # rewrite — an unfiltered channel between the check and the call. The
    # rewrite can introduce blocked terms the original never contained,
    # either because the model elaborated in an unwanted direction or
    # because the original was crafted to survive the filter and steer the
    # rewrite. Checking only the input leaves the output unexamined.
    #
    # Falls back to the (already-checked) original rather than failing the
    # request: one model's rewrite going astray should not deny the user
    # the other three.
    for _model_name, _adapted in list(adapted_prompts.items()):
        if _adapted != prompt and content_filter.check_prompt(_adapted):
            StructuredLogger.warning(
                "Adapted prompt failed the content filter; falling back to the original",
                correlation_id=correlation_id,
                model=_model_name,
            )
            adapted_prompts[_model_name] = prompt

    target = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")

    def generate_for_model(model_config):
        model_name = model_config.name
        start_time = time.time()
        iteration_index = None

        try:
            model_prompt = adapted_prompts.get(model_name, prompt)
            iteration_index = session_manager.add_iteration(
                session_id, model_name, prompt, adapted_prompt=model_prompt
            )

            handler = get_handler(model_config.provider)
            config_dict = get_model_config_dict(model_config)
            result = handler(config_dict, model_prompt, {})

            duration = time.time() - start_time

            if result["status"] == "success":
                info = _handle_successful_result(
                    session_id,
                    model_name,
                    prompt,
                    result,
                    iteration_index,
                    target,
                    duration,
                    visibility,
                    context_prompt=prompt,
                )
                return model_name, {
                    "status": "completed",
                    "imageKey": info["image_key"],
                    "imageUrl": info["image_url"],
                    "iteration": iteration_index,
                    "duration": duration,
                }
            else:
                error_msg = sanitize_error_message(result.get("error", "Unknown error"))
                _handle_failed_result(session_id, model_name, iteration_index, error_msg)
                return model_name, {
                    "status": "error",
                    "error": error_msg,
                    "iteration": iteration_index,
                }

        except Exception as e:
            sanitized = sanitize_error_message(e)
            if iteration_index is not None:
                try:
                    _handle_failed_result(session_id, model_name, iteration_index, sanitized)
                except Exception as fail_err:
                    StructuredLogger.warning(
                        f"Failed to mark iteration as failed: {fail_err}",
                        correlation_id=correlation_id,
                    )
            return model_name, {"status": "error", "error": sanitized}

    # Include skipped models in results
    results.update(skipped_models)

    # Execute in parallel using module-level executor
    futures = {_executor.submit(generate_for_model, model): model for model in models_to_dispatch}
    future_timeout = config.generate_dispatch_budget_seconds
    try:
        for future in as_completed(futures, timeout=future_timeout):
            try:
                model_name, result = future.result()
                results[model_name] = result
            except Exception as e:
                model_name = futures[future].name
                sanitized = sanitize_error_message(e)
                StructuredLogger.error(
                    f"Thread pool failure for {model_name}: {sanitized}",
                    correlation_id=correlation_id,
                )
                results[model_name] = {"status": "error", "error": sanitized}
    except TimeoutError:
        # Cancel what can still be cancelled. A future that has already
        # started cannot be stopped -- the provider call is blocking I/O
        # inside a worker thread -- so this only helps when there are more
        # models than workers. The real defence is that every provider
        # bounds its own call below this budget, so nothing should still
        # be running by the time we get here. Nova was unbounded until
        # this change, which is exactly how work outlived the budget,
        # completed, and was billed after the user was told it failed.
        # Counted from the futures themselves, not from len(results):
        # `results` already holds the skipped models, which were never
        # dispatched, so subtracting it undercounts by that many and can
        # go negative -- silencing the log in exactly the case it exists
        # for (models capped, one real call still burning money).
        cancelled = sum(1 for f in futures if f.cancel())
        still_running = sum(1 for f in futures if not f.cancelled() and not f.done())
        if still_running > 0:
            StructuredLogger.error(
                "Dispatch budget expired with provider calls still running; "
                "they will complete and be billed",
                correlation_id=correlation_id,
                stillRunning=still_running,
                cancelled=cancelled,
            )

        # Mark any models that didn't complete in time
        for future, model_cfg in futures.items():
            model_name = model_cfg.name
            if model_name not in results:
                StructuredLogger.error(
                    f"Model {model_name} timed out after {future_timeout}s",
                    correlation_id=correlation_id,
                )
                results[model_name] = {
                    "status": "error",
                    "error": f"Model timed out after {future_timeout}s",
                }

    # Nothing generated at all: the user paid for a result they did not
    # get. Skipped models do not count as attempts, so an all-skipped
    # request refunds too.
    produced = [
        r
        for name, r in results.items()
        if name not in skipped_models and r.get("status") != "error"
    ]
    if not produced:
        _refund_usage(tier_ctx, "generate", correlation_id)

    # Meter what this request cost in dollars. Every dispatched model is
    # metered, including ones that errored or timed out: the provider
    # performed the work and bills for it regardless of whether we managed
    # to return it to the user (see the as_completed timeout above, which
    # does not cancel in-flight futures). For a spend ceiling, over-counting
    # is the safe direction — under-counting means unbounded spend.
    _cost_meter.record_models(
        model_names=[m.name for m in models_to_dispatch],
        operation="generate",
        tier=tier_ctx.tier if tier_ctx else "anon",
        user_id=tier_ctx.user_id if tier_ctx else None,
        # Only bill for the adaptation when one actually happened. The
        # enhancer short-circuits to the raw prompt with no LLM call when
        # PROMPT_MODEL_API_KEY is unset — a supported open-source setup —
        # and booking phantom spend there would corrupt the cost data this
        # meter exists to gather.
        include_enhance=prompt_enhancer.is_available,
    )

    # Emitted regardless of auth: knowing which provider is slow or
    # failing has nothing to do with whether the caller logged in.
    for mname, mresult in results.items():
        if mname in skipped_models:
            continue
        dur = mresult.get("duration", 0) * 1000  # seconds to ms
        is_err = mresult.get("status") == "error"
        emit_request_metric("/generate", mname, dur, is_err)

    return results


def handle_generate(event: LambdaEvent, correlation_id: str | None = None) -> ApiResponse:
    """
    POST /generate - Create new session and generate initial images.

    Request body:
        {"prompt": "text prompt", "ip": "client IP"}

    Returns:
        {"sessionId": "uuid", "models": {...}}
    """
    validated, err = _parse_and_validate_request(
        event, require_prompt=True, endpoint_kind="generate"
    )
    if err:
        return err

    try:
        prompt = validated.prompt

        # Get enabled models
        enabled_models = get_enabled_models()
        if not enabled_models:
            _refund_usage(validated.tier, "generate", correlation_id)
            return response(500, {"error": "No models enabled"})

        # Filter models by runtime disable and per-model cost ceiling
        models_to_dispatch = []
        skipped_models = {}
        # Cost caps are deliberately unconditional: an unauthenticated
        # deployment still pays the provider, so gating this on auth was the
        # same conflation that made "open" mean "unlimited".
        now_ts = int(time.time())
        try:
            for model in enabled_models:
                # Runtime disable check (admin-toggled via DynamoDB). Shared
                # with /iterate and /outpaint so a kill switch means the same
                # thing on every path that can spend money on a model.
                if _model_runtime_disabled(model.name, correlation_id):
                    skipped_models[model.name] = {
                        "status": "skipped",
                        "reason": "admin_disabled",
                    }
                    continue
                # Per-model cost ceiling check. This is a RESERVATION and it
                # stays in the request path: consuming the slot after the
                # caller has been answered would let concurrent requests
                # overdraw the cap.
                if _model_counter_service.consume_model_slot(model.name, now_ts):
                    models_to_dispatch.append(model)
                else:
                    skipped_models[model.name] = {
                        "status": "skipped",
                        "reason": "daily_cap_reached",
                    }
        except Exception as e:
            # Fail OPEN, consistent with the quota and spend-ceiling checks: an
            # unreachable counter store is not evidence a model is over its
            # cap, and refusing every generation because DynamoDB hiccuped
            # would be a self-inflicted outage. Logged at ERROR so a persistent
            # failure — which means silently uncapped models — is alarmable.
            StructuredLogger.error(
                f"Per-model cap check failed, dispatching all models: {e}",
                correlation_id=correlation_id,
            )
            models_to_dispatch = list(enabled_models)
            skipped_models = {}

        if not models_to_dispatch:
            _refund_usage(validated.tier, "generate", correlation_id)
            return response(429, error_responses.model_cost_ceiling())

        enabled_model_names = [m.name for m in models_to_dispatch]

        # Create session
        visibility = _visibility_for_tier(validated.tier.tier if validated.tier else None)
        owner_id = (
            validated.tier.user_id if validated.tier and validated.tier.is_authenticated else None
        )
        session_id = session_manager.create_session(
            prompt,
            enabled_model_names,
            owner_id=owner_id,
            visibility=visibility,
        )

        # Record prompt history (best-effort, do not fail generation)
        try:
            user_id = validated.tier.user_id if validated.tier.is_authenticated else None
            _prompt_history.record_prompt(
                user_id=user_id,
                prompt=prompt,
                session_id=session_id,
                publish_to_feed=(visibility == "public"),
            )
        except Exception as e:
            StructuredLogger.warning(
                f"Failed to record prompt history: {e}",
                correlation_id=correlation_id,
            )

        StructuredLogger.info(
            f"Session {session_id} created",
            correlation_id=correlation_id,
            sessionId=session_id,
            models=enabled_model_names,
        )

        # Everything below this line is provider work, and none of it is
        # allowed to depend on the HTTP event. JSON-serialisable only: in
        # asynchronous mode this crosses an Invoke boundary.
        worker_payload: dict[str, Any] = {
            "source": "generate_worker",
            "sessionId": session_id,
            "prompt": prompt,
            "modelNames": enabled_model_names,
            "skipped": skipped_models,
            "visibility": visibility,
            "tier": validated.tier.tier if validated.tier else None,
            "userId": validated.tier.user_id if validated.tier else None,
            "correlationId": correlation_id,
        }

        # Computed in the request path because the worker cannot set cookies.
        set_cookie = None
        if (
            validated.tier
            and validated.tier.issue_guest_cookie
            and validated.tier.new_guest_token
            and _guest_service is not None
        ):
            set_cookie = _guest_service.set_cookie_header(
                validated.tier.new_guest_token, config.guest_window_seconds
            )

        if config.generate_async and _dispatch_generation_async(worker_payload, correlation_id):
            # No `session` key, deliberately. GenerationPanel's `else` branch
            # builds a placeholder session and hands over to useSessionPolling,
            # which is the path the client already took whenever a session was
            # not attached -- so this needed no frontend change.
            #
            # Skipped entries keep their existing {"status": "skipped",
            # "reason": ...} shape: a skipped model never becomes a session
            # iteration, so this response is the only place the cap and
            # admin-disable signals exist.
            return response(
                202,
                {
                    "sessionId": session_id,
                    "prompt": prompt,
                    "models": {
                        **skipped_models,
                        **{name: {"status": "pending"} for name in enabled_model_names},
                    },
                },
                set_cookie=set_cookie,
            )

        # Synchronous mode, or an Invoke that did not land.
        results = run_generation(worker_payload)

        # Return the finished session, not just per-model outcomes. Every
        # future has already been awaited above, so this state is final —
        # the client previously discarded this response, built empty
        # placeholders, and re-fetched the identical data by polling /status
        # every 2s for up to 5 minutes.
        #
        # `models` is retained alongside it because it carries the skipped/
        # daily_cap_reached entries, which never become session iterations.
        payload: dict[str, Any] = {
            "sessionId": session_id,
            "prompt": prompt,
            "models": results,
        }
        try:
            final_session = session_manager.get_session(session_id)
            # isinstance, not truthiness: get_session is typed to return a
            # dict or None, and attaching anything else would fail at JSON
            # serialisation — after the images are already generated and paid
            # for, and outside any handler that could recover.
            #
            # Only attach a TERMINAL session. as_completed's timeout does not
            # cancel in-flight futures, so a model can still be running and
            # writing results after this point. Attaching a pending session
            # would tell the client to stop polling for work that has not
            # finished, and it would never see the images that arrive later.
            if isinstance(final_session, dict):
                if final_session.get("status") in _TERMINAL_SESSION_STATUSES:
                    payload["session"] = _session_with_urls(final_session)
                else:
                    StructuredLogger.info(
                        "Session still in progress at response time; "
                        "client will poll for the remainder",
                        correlation_id=correlation_id,
                        sessionId=session_id,
                        sessionStatus=final_session.get("status"),
                    )
        except Exception as e:
            # The session payload is an optimisation, not the result. The
            # images are already generated and stored; failing the whole
            # response because the read-back hiccuped would throw away work
            # the user already paid for. Omitting it degrades to the previous
            # behaviour — the client falls back to polling /status.
            StructuredLogger.warning(
                f"Could not attach session to generate response: {e}",
                correlation_id=correlation_id,
                sessionId=session_id,
            )
        return response(200, payload, set_cookie=set_cookie)

    except Exception as e:
        StructuredLogger.error(
            f"Error in handle_generate: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, error_responses.internal_server_error())


def _validate_refinement_request(
    validated: ValidatedRequest,
) -> tuple[tuple[str, str, Any] | None, ApiResponse | None]:
    """Validate common fields for iterate/outpaint: sessionId, model, model config.

    Returns:
        ((session_id, model_name, model_config), None) on success,
        or (None, error_response) on failure.
    """
    body = validated.body
    session_id = body.get("sessionId")
    model_name = body.get("model")

    if not session_id:
        return None, response(400, {"error": "sessionId is required"})
    if not re.match(r"^[a-zA-Z0-9\-]{1,64}$", session_id):
        return None, response(400, {"error": "Invalid session ID format"})
    if not model_name:
        return None, response(400, {"error": "model is required"})
    if model_name not in MODELS:
        return None, response(400, {"error": f"Invalid model: {model_name}"})

    try:
        model_config = get_model(model_name)
    except ValueError as e:
        return None, response(400, {"error": str(e)})

    return (session_id, model_name, model_config), None


def _load_source_image(
    session_id: str,
    model_name: str,
    tier_ctx: Any = None,
) -> tuple[tuple[str, int, str] | None, ApiResponse | None]:
    """Authorize the session, check the iteration limit, load the source image.

    Refinement is a read of the session's latest image, so a private session
    has to be authorized here too. Guarding only the obvious viewing endpoints
    would leave /iterate and /outpaint as a way to read a private image by
    refining it.

    Returns:
        ((source_image_base64, iteration_count, visibility), None) on success,
        or (None, error_response) on failure.
    """
    # Single S3 read: load session once and derive iteration count + image key
    session = session_manager.get_session(session_id)
    if not session:
        return None, response(404, {"error": f"Session {session_id} not found"})

    if _session_is_private(session) and not _caller_owns_session(session, tier_ctx):
        # 404, not 403: confirming a session exists is itself a disclosure.
        return None, response(404, {"error": f"Session {session_id} not found"})

    visibility = session.get("visibility", "public")
    model_data = session.get("models", {}).get(model_name) or {}
    iteration_count = model_data.get("iterationCount", 0)
    if iteration_count >= MAX_ITERATIONS:
        return None, response(
            400,
            {
                "error": f"Iteration limit ({MAX_ITERATIONS}) reached for {model_name}",
            },
        )

    completed = [
        it
        for it in model_data.get("iterations", [])
        if it.get("status") == "completed" and it.get("imageKey")
    ]
    source_image_key = None
    if completed:
        source_image_key = max(completed, key=lambda x: x["index"]).get("imageKey")
    if not source_image_key:
        return None, response(400, {"error": f"No source image for {model_name}"})

    # For new .png keys: read raw bytes directly (skip JSON parse overhead)
    # For old .json keys: read JSON and extract the base64 output field
    if not source_image_key.endswith(".json"):
        raw_bytes = image_storage.get_image_bytes(source_image_key)
        if not raw_bytes:
            return None, response(500, {"error": "Failed to load source image"})
        return (base64.b64encode(raw_bytes).decode("utf-8"), iteration_count, visibility), None

    source_data = image_storage.get_image(source_image_key)
    if not source_data or not source_data.get("output"):
        return None, response(500, {"error": "Failed to load source image"})

    return (source_data["output"], iteration_count, visibility), None


def _handle_refinement(
    validated: ValidatedRequest,
    correlation_id: str | None,
    handler_name: str,
    get_handler_fn,
    build_handler_args_fn,
    add_iteration_kwargs: dict[str, Any] | None = None,
    result_prompt_fn=None,
    context_prompt_fn=None,
    extra_response_fields: dict[str, Any] | None = None,
) -> ApiResponse:
    """Unified dispatch-try-except-result flow for iterate and outpaint.

    Args:
        validated: Pre-validated request data.
        correlation_id: Request correlation ID.
        handler_name: Name for error logging (e.g. "handle_iterate").
        get_handler_fn: Callable(provider) -> handler function.
        build_handler_args_fn: Callable(config_dict, source_image, prompt, session_id,
            model_name) -> tuple of handler args.
        add_iteration_kwargs: Extra kwargs for session_manager.add_iteration().
        result_prompt_fn: Optional callable(prompt) -> prompt string for result storage.
        context_prompt_fn: Optional callable(prompt) -> context prompt string.
        extra_response_fields: Extra fields to include in success response.
    """
    iteration_index = None
    session_id = model_name = None
    # Same flag that selects the price, so a refund can never differ from the
    # charge.
    refund_kind = "outpaint" if (add_iteration_kwargs or {}).get("is_outpaint") else "refine"
    try:
        refs, err = _validate_refinement_request(validated)
        if err:
            _refund_usage(validated.tier, refund_kind, correlation_id)
            return err
        session_id, model_name, model_config = refs

        # Runtime kill switch, checked before anything is spent or written:
        # before the per-model cap slot is consumed (burning budget on a
        # request that produces nothing), before add_iteration writes an
        # in_progress row this early return would strand, and before the S3
        # read in _load_source_image. Refunds, per the _refund_usage
        # invariant -- this is exactly the class of early exit it warns about.
        if _model_runtime_disabled(model_name, correlation_id):
            StructuredLogger.warning(
                f"Refusing {handler_name} for {model_name}: disabled at runtime",
                correlation_id=correlation_id,
                sessionId=session_id,
            )
            _refund_usage(validated.tier, refund_kind, correlation_id)
            return response(503, error_responses.model_disabled(model_name))

        loaded, err = _load_source_image(session_id, model_name, validated.tier)
        if err:
            _refund_usage(validated.tier, refund_kind, correlation_id)
            return err
        source_image, iteration_count, visibility = loaded

        # Iteration warning at threshold
        warning = None
        if iteration_count >= ITERATION_WARNING_THRESHOLD:
            remaining = MAX_ITERATIONS - iteration_count
            warning = f"Only {remaining} iterations remaining for {model_name}"

        prompt = validated.prompt
        start_time = time.time()

        iter_kwargs = add_iteration_kwargs or {}
        iteration_index = session_manager.add_iteration(
            session_id,
            model_name,
            prompt,
            **iter_kwargs,
        )

        # Per-model daily cap, consumed BEFORE dispatching to the provider.
        # Previously only /generate consumed slots, so refinement traffic could
        # run a model far past its ceiling.
        try:
            slot_ok = _model_counter_service.consume_model_slot(model_name, int(time.time()))
        except Exception as e:
            StructuredLogger.error(
                f"Per-model cap check failed, allowing refinement: {e}",
                correlation_id=correlation_id,
            )
            slot_ok = True
        if not slot_ok:
            _refund_usage(validated.tier, refund_kind, correlation_id)
            return response(429, error_responses.model_cost_ceiling())

        config_dict = get_model_config_dict(model_config)
        handler = get_handler_fn(model_config.provider)
        handler_args = build_handler_args_fn(
            config_dict,
            source_image,
            prompt,
            session_id,
            model_name,
        )
        result = handler(*handler_args)

        duration = time.time() - start_time
        target = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")
        is_error = result["status"] != "success"

        # Meter the provider call. Charged whether or not it succeeded — the
        # provider ran the model either way. "refine" prices both /iterate and
        # /outpaint; they are one image on one model in both cases.
        _cost_meter.record_models(
            model_names=[model_name],
            operation="outpaint" if (add_iteration_kwargs or {}).get("is_outpaint") else "refine",
            tier=validated.tier.tier if validated.tier else "anon",
            user_id=validated.tier.user_id if validated.tier else None,
        )

        # Emitted regardless of auth, as above.
        emit_request_metric(
            f"/{handler_name.replace('handle_', '')}",
            model_name,
            duration * 1000,
            is_error,
        )

        if result["status"] == "success":
            # Refining is the first moment a user picks between four models,
            # and it costs them something, which makes it a stronger signal
            # than a click. Best-effort: product data must never fail a
            # refinement the user has already paid for.
            try:
                if validated.tier:
                    _user_repo.record_model_choice(validated.tier.user_id, model_name)
            except Exception as e:
                StructuredLogger.warning(
                    f"Could not record model choice: {e}",
                    correlation_id=correlation_id,
                )

            store_prompt = result_prompt_fn(prompt) if result_prompt_fn else prompt
            ctx_prompt = context_prompt_fn(prompt) if context_prompt_fn else None
            info = _handle_successful_result(
                session_id,
                model_name,
                store_prompt,
                result,
                iteration_index,
                target,
                duration,
                visibility,
                context_prompt=ctx_prompt,
            )
            resp = {
                "status": "completed",
                "imageKey": info["image_key"],
                "imageUrl": info["image_url"],
                "iteration": iteration_index,
                "iterationCount": iteration_index + 1,
                "duration": duration,
            }
            if warning:
                resp["warning"] = warning
            if extra_response_fields:
                resp.update(extra_response_fields)
            return response(200, resp)
        else:
            error_msg = sanitize_error_message(result.get("error", "Unknown error"))
            _handle_failed_result(session_id, model_name, iteration_index, error_msg)
            # One model, and it failed: the whole request produced nothing.
            _refund_usage(validated.tier, refund_kind, correlation_id)
            return response(
                500,
                {
                    "status": "error",
                    "error": error_msg,
                    "iteration": iteration_index,
                },
            )

    except Exception as e:
        if iteration_index is not None:
            try:
                _handle_failed_result(
                    session_id, model_name, iteration_index, sanitize_error_message(e)
                )
            except Exception as fail_err:
                StructuredLogger.warning(
                    f"Failed to mark iteration as failed: {fail_err}",
                    correlation_id=correlation_id,
                )
        StructuredLogger.error(
            f"Error in {handler_name}: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        _refund_usage(validated.tier, refund_kind, correlation_id)
        return response(500, error_responses.internal_server_error())


def handle_iterate(event: LambdaEvent, correlation_id: str | None = None) -> ApiResponse:
    """POST /iterate - Iterate on existing image with new prompt."""
    validated, err = _parse_and_validate_request(event, require_prompt=True, endpoint_kind="refine")
    if err:
        return err

    def _build_args(config_dict, source_image, prompt, session_id, model_name):
        context = context_manager.get_context_for_iteration(session_id, model_name)
        return (config_dict, source_image, prompt, context)

    return _handle_refinement(
        validated,
        correlation_id,
        "handle_iterate",
        get_handler_fn=get_iterate_handler,
        build_handler_args_fn=_build_args,
    )


def handle_outpaint(event: LambdaEvent, correlation_id: str | None = None) -> ApiResponse:
    """POST /outpaint - Expand image to new aspect ratio."""
    validated, err = _parse_and_validate_request(
        event,
        require_prompt=False,
        default_prompt="continue the scene naturally",
        # Its own kind, not "refine": CREDITS_PER_OUTPAINT is independently
        # configurable and advertised on GET /pricing, so charging the refine
        # rate here would let the advertised price drift from the charged one.
        endpoint_kind="outpaint",
    )
    if err:
        return err

    preset = validated.body.get("preset")
    if not preset:
        return response(400, {"error": "preset is required"})
    valid_presets = ["16:9", "9:16", "1:1", "4:3", "expand_all"]
    if preset not in valid_presets:
        return response(400, {"error": f"Invalid preset. Valid: {valid_presets}"})

    def _build_args(config_dict, source_image, prompt, session_id, model_name):
        return (config_dict, source_image, preset, prompt)

    return _handle_refinement(
        validated,
        correlation_id,
        "handle_outpaint",
        get_handler_fn=get_outpaint_handler,
        build_handler_args_fn=_build_args,
        add_iteration_kwargs={"is_outpaint": True, "outpaint_preset": preset},
        result_prompt_fn=lambda p: f"outpaint:{preset} - {p}",
        context_prompt_fn=lambda p: f"outpaint:{preset}",
        extra_response_fields={"preset": preset},
    )


# Statuses from SessionManager._compute_session_status that mean no model is
# still running. Anything else ("pending", "in_progress") means work may yet
# land, so the client must keep polling.
_TERMINAL_SESSION_STATUSES = frozenset({"completed", "partial", "failed"})


# Tiers whose generations are private. Paying for the product buys privacy;
# free and anonymous use feeds the public gallery, which is what makes the
# gallery worth browsing at all.
_PRIVATE_TIERS = frozenset({"paid"})

# How long a presigned image URL stays valid. Long enough to view and refine a
# session without re-fetching, short enough that a leaked URL expires.
_PRIVATE_URL_TTL_SECONDS = 3600


def _visibility_for_tier(tier: str | None) -> str:
    """Map a tier to the visibility its generations get."""
    return "private" if tier in _PRIVATE_TIERS else "public"


def _session_is_private(session: dict[str, Any]) -> bool:
    """Return True if ``session`` may only be read by its owner.

    Sessions created before visibility existed have neither field and are
    public, which matches how they were actually served.
    """
    return session.get("visibility") == "private"


def _caller_owns_session(session: dict[str, Any], tier_ctx: Any) -> bool:
    """Return True if ``tier_ctx`` identifies the owner of ``session``.

    An anonymous caller never owns anything: a session with no recorded owner
    is not "owned by whoever asks", it is unauthenticated legacy data, and it
    is only reachable here if it is also public.
    """
    owner_id = session.get("ownerId")
    if not owner_id or tier_ctx is None:
        return False
    return bool(getattr(tier_ctx, "is_authenticated", False)) and (
        getattr(tier_ctx, "user_id", None) == owner_id
    )


def _session_with_urls(session: dict[str, Any]) -> dict[str, Any]:
    """Add image URLs to completed iterations.

    Shared by /status and /generate so the two cannot return differently
    shaped sessions — the client treats them as the same object.

    Private images live outside the CloudFront origin policy and have no
    unsigned URL, so they are presigned here. Callers must authorize the
    session before calling this; issuing a presigned URL is granting access.
    """
    for _model_name, model_data in session.get("models", {}).items():
        for iteration in model_data.get("iterations", []):
            if iteration.get("status") == "completed" and iteration.get("imageKey"):
                key = iteration["imageKey"]
                if image_storage.is_private_key(key):
                    iteration["imageUrl"] = image_storage.generate_presigned_view_url(
                        key, expires_in=_PRIVATE_URL_TTL_SECONDS
                    )
                else:
                    iteration["imageUrl"] = image_storage.get_cloudfront_url(key)
    return session


def handle_status(event: LambdaEvent, correlation_id: str | None = None) -> ApiResponse:
    """
    GET /status/{sessionId} - Get session status and results.

    Returns session status with all model states and iterations.
    """
    try:
        path = event.get("rawPath", event.get("path", ""))
        session_id = path.split("/")[-1]

        # Validate session_id format (alphanumeric + hyphens, max 64 chars)
        if not session_id or not re.match(r"^[a-zA-Z0-9\-]{1,64}$", session_id):
            return response(400, {"error": "Invalid session ID format"})

        session = session_manager.get_session(session_id)
        if not session:
            return response(404, {"error": f"Session {session_id} not found"})

        # A private session is readable only by its owner. 404 rather than 403:
        # a 403 confirms the session exists, which is itself a disclosure.
        if _session_is_private(session) and not _caller_owns_session(
            session, resolve_tier(event, _user_repo, _guest_service)
        ):
            return response(404, {"error": f"Session {session_id} not found"})

        return response(200, _session_with_urls(session))

    except Exception as e:
        StructuredLogger.error(
            f"Error in handle_status: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, error_responses.internal_server_error())


def handle_enhance(event: LambdaEvent, correlation_id: str | None = None) -> ApiResponse:
    """POST /enhance - Enhance prompt using configured LLM."""
    validated, err = _parse_and_validate_request(
        event,
        require_prompt=True,
        max_prompt_length=500,
        # "enhance" subjects this to the global spend ceiling without pulling
        # in captcha or quota (both of which gate on generate/refine). It is
        # still unauthenticated — closing that is P0-D.
        endpoint_kind="enhance",
    )
    if err:
        return err

    try:
        # Two genuinely different variants from one call. This used to return
        # the same string twice while the UI rendered a toggle over it.
        short_prompt, long_prompt = prompt_enhancer.enhance_variants(validated.prompt)
        # /enhance is still unauthenticated and unquota'd (that is P0-D), but
        # it calls gpt-4o and therefore costs money. Metering it first means
        # the exposure is at least visible before it is gated.
        _cost_meter.record(
            costs={"enhance": config.enhance_cost_usd_micros},
            tier=validated.tier.tier if validated.tier else "anon",
            user_id=validated.tier.user_id if validated.tier else None,
        )

        return response(
            200,
            {
                "original": validated.prompt,
                "short_prompt": short_prompt,
                "long_prompt": long_prompt,
            },
        )

    except Exception as e:
        StructuredLogger.error(
            f"Error in handle_enhance: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, error_responses.internal_server_error())


def handle_gallery_list(event: LambdaEvent, correlation_id: str | None = None) -> ApiResponse:
    """GET /gallery/list - List all galleries with preview images."""
    try:
        gallery_folders = image_storage.list_galleries()

        def _build_gallery_entry(folder):
            images = image_storage.list_gallery_images(folder)

            preview_url = None
            # Prefer .png images for previews (browsers can't render .json)
            png_images = [img for img in images if img.endswith(".png")]
            preview_candidate = png_images[0] if png_images else (images[0] if images else None)
            if preview_candidate:
                preview_url = image_storage.get_cloudfront_url(preview_candidate)

            timestamp_str = f"{folder[:10]}T{folder[11:13]}:{folder[14:16]}:{folder[17:19]}Z"

            return {
                "id": folder,
                "timestamp": timestamp_str,
                "previewUrl": preview_url,
                "imageCount": len(images),
            }

        # Fetch gallery entries in parallel (using dedicated gallery executor)
        galleries = []
        futures = {_gallery_executor.submit(_build_gallery_entry, f): f for f in gallery_folders}
        for future in as_completed(futures):
            try:
                galleries.append(future.result())
            except Exception as e:
                StructuredLogger.warning(
                    f"Failed to load gallery {futures[future]}: {e}",
                    correlation_id=correlation_id,
                )

        # Sort by ID (timestamp) descending
        galleries.sort(key=lambda g: g["id"], reverse=True)

        return response(200, {"galleries": galleries, "total": len(galleries)})

    except Exception as e:
        StructuredLogger.error(
            f"Error in handle_gallery_list: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, {"error": "Internal server error"})


def handle_log_endpoint(event: LambdaEvent) -> ApiResponse:
    """POST /log - Accept frontend error logs."""
    raw_body = event.get("body", "")
    if len(raw_body) > MAX_LOG_BODY_SIZE:
        return response(413, {"error": "Request body too large"})

    try:
        body = json.loads(raw_body or "{}")
        ip = event.get("requestContext", {}).get("http", {}).get("sourceIp", "unknown")

        # /log relies on API Gateway throttling (not per-tier quotas).

        # Sanitize metadata: remove reserved keys that could overwrite structured log fields
        if "metadata" in body and isinstance(body["metadata"], dict):
            body["metadata"] = {
                k: v for k, v in body["metadata"].items() if k not in _RESERVED_LOG_METADATA_KEYS
            }

        headers = event.get("headers", {})
        correlation_id = headers.get("x-correlation-id") or headers.get("X-Correlation-ID")

        result = handle_log(body, correlation_id, ip)
        return response(200, result)

    except json.JSONDecodeError:
        return response(400, {"error": "Invalid JSON in request body"})
    except ValueError as e:
        return response(400, {"error": str(e)})
    except Exception as e:
        StructuredLogger.error(
            f"Error in handle_log_endpoint: {e}",
            traceback=traceback.format_exc(),
        )
        return response(500, {"error": "Internal server error"})


def handle_download(event: LambdaEvent, correlation_id: str | None = None) -> ApiResponse:
    """GET /download/{sessionId}/{model}/{iterationIndex} - Presigned download URL."""
    try:
        path = event.get("rawPath", event.get("path", ""))
        parts = path.strip("/").split("/")
        # Strip stage prefix if present (e.g. Prod/download/... -> download/...)
        if len(parts) == 5 and parts[0] not in ("download",):
            parts = parts[1:]
        # Expected: ["download", sessionId, model, iterationIndex]
        if len(parts) != 4:
            return response(400, {"error": "Invalid download path"})

        _, session_id, model_name, iter_idx_str = parts

        # Validate session ID format
        if not re.match(r"^[a-zA-Z0-9\-]{1,64}$", session_id):
            return response(400, {"error": "Invalid session ID format"})

        # Validate model
        if model_name not in MODELS:
            return response(400, {"error": f"Invalid model: {model_name}"})

        # Validate iteration index
        try:
            iteration_index = int(iter_idx_str)
            if iteration_index < 0:
                raise ValueError
        except (ValueError, TypeError):
            return response(400, {"error": "Invalid iteration index"})

        # Load session
        session = session_manager.get_session(session_id)
        if not session:
            return response(404, {"error": f"Session {session_id} not found"})

        # Same ownership rule as /status. A download URL is a grant of access,
        # so this endpoint needs the check just as much as the viewing one.
        if _session_is_private(session) and not _caller_owns_session(
            session, resolve_tier(event, _user_repo, _guest_service)
        ):
            return response(404, {"error": f"Session {session_id} not found"})

        # Find the iteration
        model_data = session.get("models", {}).get(model_name) or {}
        iterations = model_data.get("iterations", [])
        target_iter = None
        for it in iterations:
            if it.get("index") == iteration_index and it.get("status") == "completed":
                target_iter = it
                break

        if not target_iter or not target_iter.get("imageKey"):
            return response(404, {"error": "Iteration not found or not completed"})

        image_key = target_iter["imageKey"]

        # Legacy JSON-format images cannot be served as PNG downloads
        if image_key.endswith(".json"):
            return response(
                410,
                {"error": "This iteration uses a legacy format that cannot be downloaded directly"},
            )

        filename = f"{model_name}-iteration-{iteration_index}.png"

        url = image_storage.generate_presigned_download_url(image_key, filename)
        return response(200, {"url": url, "filename": filename})

    except Exception as e:
        StructuredLogger.error(
            f"Error in handle_download: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, {"error": "Internal server error"})


def handle_gallery_detail(event: LambdaEvent, correlation_id: str | None = None) -> ApiResponse:
    """GET /gallery/{galleryId} - Get all images from a specific gallery."""
    try:
        path = event.get("rawPath", event.get("path", ""))
        gallery_id = path.split("/")[-1]

        if not gallery_id:
            return response(400, {"error": "Gallery ID is required"})

        if not image_storage.validate_gallery_id(gallery_id):
            return response(400, {"error": "Invalid gallery ID format"})

        image_keys = image_storage.list_gallery_images(gallery_id)

        def _load_image(key):
            if key.endswith(".json"):
                # Old format: metadata embedded in the JSON file
                metadata = image_storage.get_image_metadata(key)
                if metadata:
                    return {
                        "key": key,
                        "url": image_storage.get_cloudfront_url(key),
                        "model": metadata.get("model", "Unknown"),
                        "prompt": metadata.get("prompt", ""),
                        "timestamp": metadata.get("timestamp"),
                    }
                return None

            # New .png format: match model name against known MODELS
            # Key format: sessions/{galleryId}/{model}-{timestamp}{-iter{N}}.png
            filename = key.rsplit("/", 1)[-1]  # e.g. "gemini-20250116100000-iter0.png"
            name_part = filename.rsplit(".", 1)[0]  # strip .png
            model_name = "Unknown"
            for m in sorted(MODELS, key=len, reverse=True):
                if name_part.startswith(m + "-") or name_part == m:
                    model_name = m
                    break
            return {
                "key": key,
                "url": image_storage.get_cloudfront_url(key),
                "model": model_name,
                "prompt": "",
                "timestamp": None,
            }

        # Fetch image metadata in parallel (using dedicated gallery executor)
        images = []
        futures = {_gallery_executor.submit(_load_image, key): key for key in image_keys}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    images.append(result)
            except Exception as e:
                StructuredLogger.warning(
                    f"Failed to load image {futures[future]}: {e}",
                    correlation_id=correlation_id,
                )

        return response(
            200,
            {
                "galleryId": gallery_id,
                "images": images,
                "total": len(images),
            },
        )

    except Exception as e:
        StructuredLogger.error(
            f"Error in handle_gallery_detail: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, {"error": "Internal server error"})


def handle_prompts_recent(event: LambdaEvent, correlation_id: str | None = None) -> ApiResponse:
    """GET /prompts/recent - Global recent prompt feed (no auth required)."""
    params = event.get("queryStringParameters") or {}
    try:
        limit = max(1, min(int(params.get("limit", 50)), 50))
    except (ValueError, TypeError):
        return response(400, {"error": "Invalid limit parameter"})

    try:
        items = _prompt_history.get_recent_feed(limit=limit)
        return response(200, {"prompts": items, "total": len(items)})

    except Exception as e:
        StructuredLogger.error(
            f"Error in handle_prompts_recent: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, error_responses.internal_server_error())


def handle_prompts_history(event: LambdaEvent, correlation_id: str | None = None) -> ApiResponse:
    """GET /prompts/history - Per-user prompt history (auth required)."""
    if not config.auth_enabled:
        return response(501, {"error": "GET /prompts/history not implemented"})

    if _guest_service is None:
        return response(500, error_responses.internal_server_error())

    ctx = resolve_tier(event, _user_repo, _guest_service)
    if not ctx.is_authenticated:
        return response(401, error_responses.auth_required())

    params = event.get("queryStringParameters") or {}
    try:
        limit = max(1, min(int(params.get("limit", 50)), 100))
    except (ValueError, TypeError):
        return response(400, {"error": "Invalid limit parameter"})
    q = (params.get("q") or "")[:200] or None

    try:
        if q:
            items = _prompt_history.search_user_history(ctx.user_id, q, limit=limit)
        else:
            items = _prompt_history.get_user_history(ctx.user_id, limit=limit)

        return response(200, {"prompts": items, "total": len(items)})

    except Exception as e:
        StructuredLogger.error(
            f"Error in handle_prompts_history: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, error_responses.internal_server_error())


def handle_me(event: LambdaEvent, correlation_id: str | None = None) -> ApiResponse:
    """GET /me - Return tier, quota, and billing status for the caller."""
    if not config.auth_enabled:
        return response(501, {"error": "GET /me not implemented"})

    if _guest_service is None:
        return response(500, error_responses.internal_server_error())

    ctx = resolve_tier(event, _user_repo, _guest_service)
    if not ctx.is_authenticated:
        return response(401, error_responses.auth_required())

    window_seconds = (
        config.paid_window_seconds if ctx.tier == "paid" else config.free_window_seconds
    )
    item = _user_repo.touch_quota_window(ctx.user_id, window_seconds, int(time.time()))
    window_start = int(item.get("windowStart", 0) or 0)

    if ctx.tier == "paid":
        quota = {
            "windowSeconds": config.paid_window_seconds,
            "windowStart": int(item.get("dailyResetAt", 0) or 0),
            # Reported since paid generation gained a bound: a limit the user
            # cannot see is a limit they experience as a bug.
            "generate": {
                "used": int(item.get("dailyGenerateCount", 0) or 0),
                "limit": config.paid_daily_generate_limit,
            },
            "refine": {
                "used": int(item.get("dailyCount", 0) or 0),
                "limit": config.paid_daily_limit,
            },
        }
    else:
        quota = {
            "windowSeconds": config.free_window_seconds,
            "windowStart": window_start,
            "generate": {
                "used": int(item.get("generateCount", 0) or 0),
                "limit": config.free_generate_limit,
            },
            "refine": {
                "used": int(item.get("refineCount", 0) or 0),
                "limit": config.free_refine_limit,
            },
        }

    billing = {
        "subscriptionStatus": item.get("subscriptionStatus"),
        "portalAvailable": bool(item.get("stripeCustomerId")),
    }

    # Which models this user actually refines, highest first. Generating
    # produces four images they did not choose between; refining one is the
    # preference, and it is the only per-user signal of its kind the product
    # collects.
    model_choices = _user_repo.get_model_choices(ctx.user_id)

    return response(
        200,
        {
            "userId": ctx.user_id,
            "email": ctx.email,
            "tier": ctx.tier,
            "quota": quota,
            "billing": billing,
            "groups": extract_admin_groups(event),
            "modelChoices": model_choices,
            "preferredModel": next(iter(model_choices), None),
        },
    )


def response(
    status_code: int,
    body: dict[str, Any],
    set_cookie: str | None = None,
) -> ApiResponse:
    """Helper function to create API Gateway response.

    ``retryAfter`` in the body is mirrored into a real ``Retry-After`` header.
    Mirroring here rather than at each call site means any response that
    carries the field gets the header; it does not put the field there. Only a
    caller that knows when the limit lifts can do that — the quota rejections
    in ``_parse_and_validate_request`` and ``daily_spend_ceiling``, which
    computes seconds to UTC midnight. ``model_cost_ceiling`` deliberately has
    no interval: ``consume_model_slot`` returns a bare bool, so its reset is
    not in scope at the point of refusal, and a guess would be worse than
    silence.

    The body field stays: a client already reading it must keep working, and
    the two agreeing is the point.
    """
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": cors_allowed_origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, X-Correlation-ID",
        # Without this a browser cannot read Retry-After cross-origin, which
        # would make emitting it pointless for the only client that has one.
        "Access-Control-Expose-Headers": "Retry-After, X-Correlation-ID",
    }
    retry_after = body.get("retryAfter")
    # bool is an int subclass, and True would render as "True" — a value no
    # client can parse into a delay.
    if isinstance(retry_after, int) and not isinstance(retry_after, bool) and retry_after > 0:
        headers["Retry-After"] = str(retry_after)
    resp: ApiResponse = {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body),
    }
    if set_cookie:
        resp["cookies"] = [set_cookie]
    return resp
