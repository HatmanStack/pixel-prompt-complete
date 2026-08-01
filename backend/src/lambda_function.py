"""
Main Lambda handler for Pixel Prompt v2.
Routes API requests to appropriate handlers for image generation,
iteration, outpainting, and session status.
"""

import base64
import hashlib
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
    generate_thread_workers,
    get_enabled_models,
    get_model,
    get_model_config_dict,
    s3_bucket,
)
from gallery.repository import GalleryIndexRepository
from jobs.manager import SessionManager
from models.context import ContextManager, create_context_entry
from models.providers import (
    get_handler,
    get_iterate_handler,
    get_outpaint_handler,
    sanitize_error_message,
)
from ops import store_breaker
from ops.cost_meter import CostMeter, UnreadableSpendTotal
from ops.metrics import emit_quota_rejection, emit_request_metric, emit_request_metrics
from ops.model_counters import ModelCounterService
from prompts.repository import PromptHistoryRepository
from users.quota import QuotaResult, enforce_quota
from users.repository import UserRepository
from users.tier import TierContext, anon_tier, persist_guest, resolve_tier
from utils import error_responses
from utils.content_filter import ContentFilter
from utils.http import invocation_ack, json_response
from utils.logger import StructuredLogger
from utils.storage import PUBLIC_PREFIX, ImageStorage

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

# Newest-first index of public gallery folders. Rides the same GSI as prompt
# history; see gallery/repository.py for why the read has to be indexed.
_gallery_index = GalleryIndexRepository(config.users_table_name)

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
# exists to escape.
#
# Exactly one attempt. An Event invoke is not idempotent from the caller's
# side: if Lambda accepts it but the 202 is lost or arrives after read_timeout,
# a botocore retry sends the same payload again and BOTH can be delivered. Two
# workers then run run_generation against one sessionId -- eight iterations
# instead of four, every provider called and billed twice, and _cost_meter
# double-counting. Retrying buys a second chance at a transport blip; losing
# that chance costs one inline fallback. Double-generating costs real money.
_INVOKE_CONNECT_TIMEOUT_SECONDS = 2
_INVOKE_READ_TIMEOUT_SECONDS = 5
_INVOKE_MAX_ATTEMPTS = 1


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

    Fails OPEN on a STORE error: if DynamoDB is unreachable we cannot prove
    the budget is blown, and hard-failing every billable request on a
    transient blip would be a self-inflicted outage. The read error is logged
    so the gap is visible.

    Fails CLOSED on ``UnreadableSpendTotal`` -- a successful read whose total
    is not a number. That is permanent rather than transient, so failing open
    would leave the ceiling switched off indefinitely by a stray attribute.

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
    except UnreadableSpendTotal as e:
        # Fails CLOSED, unlike the store error below. The read succeeded and
        # the number is corrupt, which is permanent: failing open here leaves
        # the ceiling off until someone reads the logs. The READ worked, so
        # this is a success as far as the store breaker is concerned.
        store_breaker.record_store_result(True)
        StructuredLogger.error(f"Spend accumulator is unreadable, refusing request: {e}")
        return True
    except Exception as e:
        store_breaker.record_store_result(False)
        StructuredLogger.error(f"Spend ceiling check failed, allowing request: {e}")
        return False
    store_breaker.record_store_result(True)
    return int(spend.get("totalMicros", 0)) >= ceiling


def _monthly_spend_exceeded(now: int | None = None) -> bool:
    """True when this calendar month's spend has reached the ceiling.

    The daily ceiling bounds a bad day; this bounds a bad month. Without it,
    sustained traffic at just under the daily limit runs to roughly 30x it.

    Fails open on a store error for the same reason as the daily check: an
    unreachable counter is not evidence the budget is blown. Fails closed on
    a corrupt total, for the reason given there.
    """
    ceiling = config.monthly_spend_ceiling_usd_micros
    if ceiling <= 0:
        return False
    try:
        spend = _cost_meter.get_monthly_spend(now=now)
    except UnreadableSpendTotal as e:
        store_breaker.record_store_result(True)
        StructuredLogger.error(f"Monthly accumulator is unreadable, refusing request: {e}")
        return True
    except Exception as e:
        store_breaker.record_store_result(False)
        StructuredLogger.error(f"Monthly ceiling check failed, allowing request: {e}")
        return False
    store_breaker.record_store_result(True)
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
    except UnreadableSpendTotal as e:
        store_breaker.record_store_result(True)
        StructuredLogger.error(f"Spend accumulator is unreadable, refusing enhance: {e}")
        return True
    except Exception as e:
        store_breaker.record_store_result(False)
        StructuredLogger.error(f"Enhance ceiling check failed, allowing request: {e}")
        return False
    store_breaker.record_store_result(True)
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
        result = enforce_quota(tier_ctx, endpoint_kind, _user_repo, now)
    except Exception as e:
        store_breaker.record_store_result(False)
        StructuredLogger.error(
            f"Quota check failed, allowing request: {e}",
            tier=tier_ctx.tier,
            endpoint=endpoint_kind,
        )
        from users.quota import QuotaResult

        return QuotaResult(allowed=True, reason=None, reset_at=0, usage={})
    # Deliberately NO record_store_result(True) here, and this is not an
    # oversight. enforce_quota delegates the anon path to
    # users.quota._enforce_anon, which catches its own store error, records
    # the failure, and returns an allowed result -- so a success recorded
    # here would immediately overwrite the failure recorded one frame down
    # and reset the consecutive counter on every request. Caught by
    # test_generate_stops_dispatching...: with the True in place the breaker
    # never tripped at all. The site closest to the store call is the one
    # that knows whether it was reached.
    return result


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

    # `anon` is metered by a call counter, never by credits -- `_enforce_anon`
    # increments generateCount/refineCount on `anon#<ip_hash>` and no credit is
    # ever debited. So it takes the counter path below whatever
    # `credits_enabled` says. Returning early for it here made every anon
    # refund inert in exactly the deployment where anon is the only tier there
    # is (CREDITS_ENABLED=true with AUTH_ENABLED=false), while
    # `_REFUND_COUNTERS` carried anon rows showing the refund was intended.
    # `guest` is excluded separately and deliberately: nothing to refund to.
    if config.credits_enabled and tier_ctx.tier != "anon":
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
            if result.reason == "guest_identity_missing":
                # 403, not the tier fall-through's 429: nothing here is a rate
                # limit, so telling the caller to wait for a window to reset is
                # advice that can never work. Signing in is the way through.
                return None, response(403, error_responses.auth_required())
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


def _source_ip_hash(event: LambdaEvent) -> str | None:
    """Stable, non-reversible bucket for the caller's source IP.

    Returns None when the event carries no address, which the callers treat
    as "cannot meter" rather than as a bucket of its own. Deliberately unlike
    ``users.tier``, which hashes the literal ``"unknown"`` so an unidentified
    caller still lands in *some* tier -- here there is no tier to fall back
    to, and metering every proxy-stripped request into one shared bucket
    would rate-limit them as if they were a single caller.
    """
    ip = (event.get("requestContext") or {}).get("http", {}).get("sourceIp")
    if not ip:
        return None
    return hashlib.sha256(str(ip).encode()).hexdigest()[:16]


def _public_ip_rate_limited(
    event: LambdaEvent,
    scope: str,
    limit: int,
    window_seconds: int,
    correlation_id: str | None = None,
) -> ApiResponse | None:
    """Bound one public endpoint per source IP. Returns a 429, or None to allow.

    For the endpoints that reach a shared billable resource without an
    identity: ``/enhance`` calls a paid LLM and ``/log`` writes billed
    CloudWatch records, and both skip tier quota. Each already had a *global*
    bound -- the enhance daily sub-ceiling, API Gateway throttling -- and a
    global bound caps everyone together, so it cannot stop one caller
    consuming the share of all the others. Exhausting the enhance allocation
    503s every legitimate enhance request until reset, which turns a cost
    guard into a denial-of-service amplifier.

    ``scope`` gives each endpoint its own bucket, so a browser reporting
    errors cannot exhaust anyone's prompt enhancement.

    Fails **open**, matching every other guard over this table: an unreachable
    counter is not evidence the caller is over limit, and failing a public
    endpoint because DynamoDB hiccuped is a self-inflicted outage. Logged at
    ERROR so persistently unmetered traffic is alarmable rather than
    invisible, and counted by the store breaker like the other six sites that
    swallow a store error.

    A ``limit`` of zero or less **disables** the check. That is the convention
    ``ENHANCE_DAILY_SPEND_CEILING_USD_MICROS`` already documents two knobs
    away, and the alternative is worse than inconsistent: the counter
    condition is ``requestCount < :limit``, so a limit of 0 fails on the very
    first request and an operator reaching for the off switch takes the
    endpoint offline for everybody instead.

    An IP is not a person. Like the anon and guest IP buckets, this is an
    abuse ceiling rather than a fair-use quota.
    """
    if limit <= 0:
        return None

    ip_hash = _source_ip_hash(event)
    if not ip_hash:
        # Nothing to meter against. Allowing is the lesser evil, exactly as in
        # users.quota._enforce_anon: denying would break every caller behind a
        # proxy that strips the address.
        return None

    now = int(time.time())
    try:
        ok, item = _user_repo.increment_ip_rate_bucket(
            f"iplimit#{scope}#{ip_hash}", limit, window_seconds, now
        )
    except Exception as e:
        store_breaker.record_store_result(False)
        StructuredLogger.error(
            f"{scope} IP rate limit check failed, allowing request: {e}",
            correlation_id=correlation_id,
        )
        return None
    store_breaker.record_store_result(True)
    if ok:
        return None

    window_start = int(item.get("windowStart", now) or now)
    retry_after = max(1, window_start + window_seconds - now)
    StructuredLogger.warning(
        f"{scope} IP rate limit reached",
        correlation_id=correlation_id,
        scope=scope,
        limit=limit,
    )
    return response(429, error_responses.ip_rate_limit(scope, retry_after=retry_after))


def _release_model_slot(model_name: str, correlation_id: str | None = None) -> None:
    """Return a per-model daily slot taken by work that never reached a provider.

    The per-user quota refund next to every call of this has a matching
    invariant; this is the shared half of it. A slot left spent is capacity
    taken from every other user of the service, not just from the caller who
    lost the race.

    Best-effort and never raised: this runs on a path that is already
    returning an error, and failing to give a slot back must not turn one
    error into two. A missed release costs one slot off a daily cap until the
    window rolls, which is the safe direction.
    """
    try:
        released = _model_counter_service.release_model_slot(model_name, int(time.time()))
        if released:
            StructuredLogger.info(
                f"Released a {model_name} slot for a refinement that never dispatched",
                correlation_id=correlation_id,
            )
    except Exception as e:
        StructuredLogger.warning(
            f"Could not release the {model_name} model slot: {e}",
            correlation_id=correlation_id,
        )


def _release_model_slots(model_names: list[str], correlation_id: str | None = None) -> None:
    """Return every per-model slot a request reserved and then never spent.

    ``/generate`` reserves one slot per model *before* the session exists, so
    a request that dies between the reservation and the worker taking it over
    leaks up to four slots off a cap shared by the whole service. The
    per-user quota is refunded on those paths already; this is the shared
    half, and the shared half is the one that costs other people.
    """
    for name in model_names:
        _release_model_slot(name, correlation_id)


def _index_public_gallery(image_key: str) -> None:
    """Record a public image's gallery folder in the bounded gallery index.

    Derived from the key rather than passed in, so the one place that decides
    an image is public -- ``ImageStorage.upload_image``, which encodes
    visibility in the prefix -- stays the only place that decides it. A
    private key has no gallery folder and is skipped structurally, not by a
    flag a future call site could forget to pass.

    Best-effort, but not consequence-free, and the docstring said otherwise
    until the read path changed underneath it. A DynamoDB failure must not
    fail a generation the user has been charged for -- so this swallows.
    There is no read-side fallback to S3 any more, though, and the backfill
    marker is already written by the time a session generates, so a dropped
    write costs that folder its place in the gallery until its retention
    expires. Logged at ERROR for that reason rather than passed over.
    """
    try:
        if image_storage.is_private_key(image_key):
            return
        parts = image_key.split("/")
        if len(parts) < 3 or parts[0] != PUBLIC_PREFIX:
            return
        folder = parts[1]
        if not image_storage.validate_gallery_id(folder):
            return
        _gallery_index.record_gallery(folder)
    except Exception as e:
        StructuredLogger.error(f"Could not index gallery folder for {image_key}: {e}")


# Folders indexed by one backfill pass. Above any plausible 30-day retention
# Folders indexed per batch write, and the wall-clock the backfill may spend
# inside one request. The deadline is what keeps the first pass from
# overrunning the gateway; the resume cursor is what stops the next request
# starting the corpus again.
_GALLERY_BACKFILL_CHUNK = 200
_GALLERY_BACKFILL_BUDGET_SECONDS = 10.0

# Per container: once the marker says complete it never goes back, so
# re-reading it on every gallery request would be a GetItem to learn a
# constant.
_gallery_backfilled = False

# The folder list a backfill is working through, held for the life of the
# container. `list_galleries()` pages the ENTIRE `sessions/` prefix -- its
# `limit` and `cursor` filter the result afterwards rather than shortening the
# walk -- so without this every resumed pass re-pays the full listing, and a
# corpus needing many passes pays it once per request. That is the same
# amplification on the same unauthenticated route this index exists to remove,
# merely scoped to the backfill window.
#
# Caching it makes the walk once-per-container instead: with ten reserved
# executions the whole backfill costs at most ten walks, not one per request.
# Folders created *during* the window are indexed live by
# `_index_public_gallery`, so a list that predates them is not stale for this
# purpose.
_gallery_backfill_pending: list[str] | None = None


def _ensure_gallery_index_backfilled(correlation_id: str | None = None) -> None:
    """Complete the index from S3, so reading it cannot hide folders.

    The index is only safe to read as the whole truth if it *is* the whole
    truth. Folders written before it shipped have no entry, so serving the
    index alone would make an existing deployment's entire gallery vanish for
    the rest of its 30-day retention -- and preferring S3 whenever the index
    looked short would just restore the unbounded scan this exists to remove.
    So the index is completed rather than second-guessed.

    **Resumable, and bounded by wall-clock rather than by count.** An earlier
    version walked the corpus and wrote up to 5000 folders in one go, marking
    the index complete at the end. That had two failure modes: a pass too slow
    to finish left no marker at all, so the next request began the whole walk
    again -- and the load is heaviest exactly when the pass is slowest -- while
    a corpus over the cap was marked complete with the oldest folders never
    indexed, hiding them permanently.

    Each pass now writes in chunks, records the oldest folder it reached, and
    stops when its budget is spent. The next request resumes from that cursor,
    so the work converges instead of restarting, and ``complete`` is written
    only when the walk is genuinely exhausted.

    Newest-first is deliberate: page one of the gallery is what a caller
    actually sees, so the first chunk makes the endpoint useful and later
    passes deepen it.

    Concurrent cold requests can each run a pass. Reserved concurrency caps
    that at ten, the writes are idempotent, and they share the cursor -- so
    they overlap rather than multiply. The alternative, a lock over the store
    this is trying not to depend on, is worse.
    """
    global _gallery_backfilled, _gallery_backfill_pending
    if _gallery_backfilled:
        return
    complete, resume_after = _gallery_index.get_backfill_state()
    if complete:
        _gallery_backfilled = True
        _gallery_backfill_pending = None
        return

    started = time.time()
    # Newest-first, and the same ordering the index uses, so `resume_after`
    # means "everything lexicographically above this is already indexed".
    #
    # Listed once per container, not once per pass. The budget below bounds
    # the writes; without this cache it would not bound the listing, and the
    # listing is the expensive half -- `list_galleries()` pages the whole
    # prefix regardless of what is asked of it.
    if _gallery_backfill_pending is None:
        _gallery_backfill_pending = image_storage.list_galleries()
    pending = _gallery_backfill_pending
    if resume_after:
        # Re-filtered rather than consumed destructively: another container
        # may have advanced the cursor further than this one's last pass.
        pending = [g for g in pending if g < resume_after]

    indexed = 0
    cursor = resume_after
    for offset in range(0, len(pending), _GALLERY_BACKFILL_CHUNK):
        chunk = pending[offset : offset + _GALLERY_BACKFILL_CHUNK]
        indexed += _gallery_index.backfill_chunk(chunk)
        cursor = chunk[-1]
        # After the chunk, never before: progress must not claim coverage that
        # was not written.
        exhausted = offset + _GALLERY_BACKFILL_CHUNK >= len(pending)
        out_of_time = time.time() - started >= _GALLERY_BACKFILL_BUDGET_SECONDS
        if exhausted or out_of_time:
            _gallery_index.record_backfill_progress(cursor, complete=exhausted)
            break
    else:
        # Nothing pending: the walk is already exhausted.
        _gallery_index.record_backfill_progress(cursor, complete=True)
        exhausted = True

    if exhausted:
        _gallery_backfilled = True
        # Released rather than left to sit for the life of the container: it
        # is a backfill scratchpad, and the backfill is over.
        _gallery_backfill_pending = None
        StructuredLogger.info(
            f"Gallery index backfill complete; indexed {indexed} folders this pass",
            correlation_id=correlation_id,
        )
    else:
        StructuredLogger.info(
            f"Gallery index backfill paused after {indexed} folders; "
            "the next request resumes from the cursor",
            correlation_id=correlation_id,
            resumeAfter=cursor,
        )


def _list_gallery_page(
    count: int, cursor: str | None, correlation_id: str | None = None
) -> list[str]:
    """Newest-first gallery ids, from the bounded index.

    One query against ``PromptHistoryIndex``, so the work is proportional to
    the page rather than to every session the service still retains.

    There is deliberately **no fallback to S3 on failure**. This endpoint is
    unauthenticated and unquota'd, and the whole point of the index is that a
    public GET cannot be made to walk the entire bucket; a fallback would hand
    that back to anyone who could make DynamoDB fail, and would do it for
    every request for the duration. Failing the request keeps the bound, and
    the caller gets a 503 they can retry.

    Raises:
        ValueError: on an unparseable cursor (surfaced as 400).
        Exception: on any index failure (surfaced as 503).
    """
    _ensure_gallery_index_backfilled(correlation_id)
    return _gallery_index.list_recent(count, cursor)


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
    _index_public_gallery(image_key)

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
        # Not an HTTP response: the worker is invoked directly, so nothing
        # reads headers here. See utils.http.invocation_ack.
        return invocation_ack()

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

    # Everything from here is accounting and observability, and none of it may
    # raise. Two reasons, and the second is the load-bearing one:
    #
    # 1. The images exist and the provider has billed for them. Failing the
    #    request because a metric write hiccuped throws away work the caller
    #    already paid for.
    # 2. handle_generate decides whether to refund by checking whether this
    #    function returned. The refund decision is made immediately above, so a
    #    raise BELOW it unwinds past that flag and the outer handler refunds a
    #    second time -- returning the charge twice for one request, or
    #    refunding a caller who did receive images.
    #
    # Both failures are already logged inside their own modules; swallowing
    # here loses nothing but the propagation.
    try:
        _record_dispatch_accounting(
            results=results,
            skipped_models=skipped_models,
            models_to_dispatch=models_to_dispatch,
            tier_ctx=tier_ctx,
        )
    except Exception as e:
        StructuredLogger.error(
            f"Accounting for a completed generation failed: {e}",
            correlation_id=correlation_id,
            sessionId=payload.get("sessionId"),
            traceback=traceback.format_exc(),
        )

    return results


def _record_dispatch_accounting(
    results: dict[str, Any],
    skipped_models: dict[str, Any],
    models_to_dispatch: list[Any],
    tier_ctx: TierContext | None,
) -> None:
    """Meter spend and emit request metrics for a finished dispatch.

    Extracted so its failure modes sit behind one guard in run_generation
    rather than on the path between the refund decision and the return.
    """
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
    #
    # One call for the whole dispatch, not one per model. Each put_metric_data
    # is bounded at 2s connect + 2s read x 2 attempts, so four models was up
    # to ~16s of blocking network time. The async move took that off the
    # request path but not out of the reserved concurrency slot or the billed
    # duration. Skipped models are excluded: they never reached a provider, so
    # reporting latency for them would report work that did not happen.
    emit_request_metrics(
        [
            (
                "/generate",
                mname,
                # Coerced, not left to Python's numeric tower. An errored
                # model returns no "duration" key -- the timer is read only on
                # the success branch -- so .get() yields the int default and an
                # int reaches a parameter declared float. That absence is how a
                # non-float got in.
                float(mresult.get("duration") or 0.0) * 1000,  # seconds to ms
                mresult.get("status") == "error",
            )
            for mname, mresult in results.items()
            if mname not in skipped_models
        ]
    )


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

    # Set once run_generation has returned, after which the refund decision is
    # already made and the outer handler must not make it again. Bound here so
    # the handler can read it however early the failure lands.
    refund_owned_downstream = False

    # Per-model cap slots this request has reserved but not yet handed to a
    # provider. Bound here for the same reason as the flag above: the failure
    # paths need to read it however early the failure lands. It stays
    # authoritative through the fail-open branch below, where slots consumed
    # before the store broke are still genuinely consumed.
    reserved_slots: list[str] = []

    try:
        # Every cost guard above this line reads one DynamoDB table and fails
        # OPEN when it is unreachable, so a partition opens all of them at
        # once and stops the spend accounting too. This is the only bound that
        # does not need that table. Checked AFTER quota -- a caller who cannot
        # generate anyway should be refused for the reason that actually
        # applies to them -- and BEFORE any provider is reached.
        #
        # Refunds on the way out, per the _refund_usage invariant: this is an
        # early exit that never reaches a provider. Phase 2 removed 503 from
        # the client's retryable set for POSTs, so this cannot be retried into.
        if store_breaker.should_shed():
            StructuredLogger.error(
                "Shedding /generate: the quota store is unreachable and this "
                "container has spent its degraded dispatch budget",
                correlation_id=correlation_id,
                **store_breaker.state(),
            )
            _refund_usage(validated.tier, "generate", correlation_id)
            return response(503, error_responses.spend_guard_degraded())

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
                    # Tracked so the failure paths below can hand it back. A
                    # slot reserved for a generation that never reaches a
                    # provider is capacity taken from every other user.
                    reserved_slots.append(model.name)
                else:
                    skipped_models[model.name] = {
                        "status": "skipped",
                        "reason": "daily_cap_reached",
                    }
            store_breaker.record_store_result(True)
        except Exception as e:
            # Fail OPEN, consistent with the quota and spend-ceiling checks: an
            # unreachable counter store is not evidence a model is over its
            # cap, and refusing every generation because DynamoDB hiccuped
            # would be a self-inflicted outage. Logged at ERROR so a persistent
            # failure — which means silently uncapped models — is alarmable.
            store_breaker.record_store_result(False)
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

        if config.generate_async and not _dispatch_generation_async(worker_payload, correlation_id):
            # Async was asked for and the Invoke did not land. Falling through
            # to the inline path looks like graceful degradation and is not:
            # run_generation carries generate_dispatch_budget_seconds (~70s)
            # and this route declares a 29s integration timeout, so the gateway
            # returns 504 at 29s while the function keeps going. The caller
            # never receives the sessionId, four providers generate and bill
            # for images that are now unreachable, and no refund fires because
            # run_generation only refunds when EVERY model errors.
            #
            # Failing fast costs one retry. The cause -- a missing
            # lambda:InvokeFunction grant, or throttling -- is an operator fact
            # already logged at ERROR by _dispatch_generation_async.
            #
            # Narrowed to generate_async deliberately: when the operator has
            # chosen synchronous mode the inline path below is the intended
            # behaviour, not a fallback, and tests/backend/e2e depends on it.
            #
            # The reserved slots go back with the quota. Without this a broken
            # lambda:InvokeFunction grant -- the exact cause this branch exists
            # for -- burns four slots per attempt off a shared daily cap, so a
            # deploy that fails every /generate would drive every model to
            # daily_cap_reached and answer 429 MODEL_COST_CEILING until
            # midnight UTC, having generated nothing.
            _release_model_slots(reserved_slots, correlation_id)
            _refund_usage(validated.tier, "generate", correlation_id)
            return response(
                503, error_responses.generation_dispatch_failed(), set_cookie=set_cookie
            )

        if config.generate_async:
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

        # Synchronous mode.
        results = run_generation(worker_payload)
        # From here on the refund decision belongs to run_generation, which
        # refunds on total failure and deliberately does not on a partial
        # result. The outer handler must not second-guess it: refunding again
        # would return the charge twice, and refunding after a partial success
        # would pay for images the caller actually received.
        refund_owned_downstream = True

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
        # Quota was consumed in _parse_and_validate_request, so this 500 owes a
        # refund like every other non-2xx below that point -- see the INVARIANT
        # on _refund_usage. create_session raising on an S3 blip, or the worker
        # payload failing to serialise, otherwise cost a free user their whole
        # FREE_WINDOW_SECONDS for an image they never got. `validated` is bound
        # before the try, so it is safe to read here.
        #
        # Guarded, not unconditional. In synchronous mode `run_generation` runs
        # inside this same `try` and owns the refund decision once it returns:
        # it refunds on total failure and deliberately withholds one on a
        # partial result. An unguarded refund here would hand the charge back
        # twice when a total failure is followed by a raise, and would refund a
        # caller who actually received images. Asynchronous mode never reaches
        # that call in the request path, so the flag is still False and the
        # refund fires -- which is the case this handler exists for.
        #
        # The reserved model slots ride the same flag. Once run_generation has
        # returned, the providers were dispatched and the slots bought exactly
        # what they exist to meter; before that -- create_session raising on an
        # S3 blip, the payload failing to serialise -- they bought nothing, and
        # holding them penalises every other user rather than this caller.
        if not refund_owned_downstream:
            _release_model_slots(reserved_slots, correlation_id)
            _refund_usage(validated.tier, "generate", correlation_id)
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
    # Hoisted above the try so the handler below can read them however early
    # the failure lands.
    slot_consumed = False
    dispatched = False
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

        # Per-model daily cap, consumed BEFORE dispatching to the provider.
        # Previously only /generate consumed slots, so refinement traffic could
        # run a model far past its ceiling.
        #
        # Ordered before `add_iteration` for the same reason the runtime kill
        # switch above it is: this branch returns without ever calling
        # `_handle_failed_result`, so an iteration row written first would stay
        # `in_progress` forever. `_compute_model_status` would report the model
        # in progress, `_compute_session_status` the session, and the client
        # would poll a spinner that never resolves while one of the model's
        # MAX_ITERATIONS slots stayed spent on work that never ran.
        #
        # That ordering leaves a gap this alone does not close. `add_iteration`
        # re-reads the session under its ETag and re-checks the iteration
        # limit, so concurrent refinements can all pass the earlier read above,
        # one wins the last slot, and the losers raise -- having already taken
        # a slot off a cap shared by every user of the service. `slot_consumed`
        # is what lets the failure paths below hand it back; `dispatched` is
        # what stops them handing it back once a provider has run, because at
        # that point the image was generated and billed whatever the outcome.
        #
        # It tracks the slot actually being taken rather than `slot_ok`: the
        # fail-open branch below reports success without incrementing anything,
        # and releasing there would decrement a counter this request never
        # touched, stealing capacity from whoever did.
        try:
            slot_ok = _model_counter_service.consume_model_slot(model_name, int(time.time()))
            slot_consumed = slot_ok
        except Exception as e:
            StructuredLogger.error(
                f"Per-model cap check failed, allowing refinement: {e}",
                correlation_id=correlation_id,
            )
            slot_ok = True
        if not slot_ok:
            _refund_usage(validated.tier, refund_kind, correlation_id)
            return response(429, error_responses.model_cost_ceiling())

        iter_kwargs = add_iteration_kwargs or {}
        iteration_index = session_manager.add_iteration(
            session_id,
            model_name,
            prompt,
            **iter_kwargs,
        )

        config_dict = get_model_config_dict(model_config)
        # The budget this provider call has to fit inside. It is the same
        # budget /generate uses, and deliberately NOT the 29s gateway ceiling.
        #
        # Sizing it to the gateway looks right -- /iterate and /outpaint are
        # answered inside the HTTP request -- but it does not survive contact
        # with the per-provider subdivision in utils/clients.py. A 25s budget
        # becomes a 5s Bedrock read timeout, 5s per Firefly call and 12s for
        # OpenAI, because each provider reserves for its own worst case
        # (retries, token round trip, image download). Image refinement
        # routinely takes 10-40s, so those bounds do not shorten slow
        # refinements: they fail all of them, mark the iteration failed, and
        # still pay the provider, which generated the image anyway.
        #
        # Overrunning the gateway is the lesser evil and is already survivable.
        # `add_iteration` has written the row, the provider result is stored
        # against it, and `useSessionPolling` observes the outcome on /status
        # regardless of what the original POST returned. A 504 there costs a
        # stale error toast; a 5s timeout costs the image and the money. The
        # durable fix is to dispatch refinement to a worker the way Phase 3 did
        # for /generate, which removes the ceiling instead of negotiating.
        config_dict["timeout"] = config.generate_dispatch_budget_seconds
        handler = get_handler_fn(model_config.provider)
        handler_args = build_handler_args_fn(
            config_dict,
            source_image,
            prompt,
            session_id,
            model_name,
        )
        # Set before the call, not after: a provider that raises mid-call may
        # well have generated and billed for the image already, so the slot
        # stays spent. Over-counting a cost ceiling is safe; under-counting is
        # the thing the ceiling exists to prevent.
        dispatched = True
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
        # The shared cap, alongside the per-user quota below. This request took
        # a model slot and never reached a provider, so the slot bought
        # nothing -- and unlike the quota, which only costs its owner, a slot
        # left spent is capacity taken from every other user of the service.
        if slot_consumed and not dispatched and model_name:
            _release_model_slot(model_name, correlation_id)
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


def _resolve_tier_or_none(event: LambdaEvent) -> TierContext | None:
    """Resolve the caller's tier, or ``None`` if identity cannot be resolved.

    ``_guest_service`` is ``None`` whenever ``GUEST_TOKEN_SECRET`` is unset,
    and with ``AUTH_ENABLED=true`` that reaches ``resolve_tier``'s guest path,
    which needs it. ``/status`` and ``/download`` were passing it straight
    through while ``/me`` and ``/prompts/history`` guarded.

    The guard is ``auth_enabled and _guest_service is None``, not
    ``_guest_service is None``: with auth off the service is legitimately
    absent and ``resolve_tier`` short-circuits before reading it, so widening
    the guard would change behaviour in a configuration that is not broken.

    These two endpoints answer ``None`` rather than 500, unlike the three
    neighbouring sites, and the difference is deliberate:

    - The write paths (``_parse_and_validate_request``) and the identity paths
      (``/me``, ``/prompts/history``) return 500, so the misconfiguration is
      loud and cannot pass unnoticed.
    - A 500 *here* would be a side channel. It separates "this session exists
      and is private" from "no such session", which is exactly the disclosure
      the 404-not-403 rule on these endpoints exists to prevent. And both
      endpoints also serve public sessions, which have nothing to do with
      guest identity: failing them would give a missing secret a blast radius
      across the whole read path, gallery included.

    ``None`` already has a defined meaning to ``_caller_owns_session``: not
    the owner. For a private session that yields the 404 those handlers
    already return.
    """
    if config.auth_enabled and _guest_service is None:
        return None
    return resolve_tier(event, _user_repo, _guest_service)


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
            session, _resolve_tier_or_none(event)
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

    # Before the LLM call, because the point of the bound is the spend. The
    # daily sub-ceiling above bounds the money in aggregate; this stops one
    # caller spending all of it and 503ing enhancement for everyone else.
    limited = _public_ip_rate_limited(
        event,
        "enhance",
        config.enhance_ip_limit,
        config.enhance_ip_window_seconds,
        correlation_id,
    )
    if limited:
        return limited

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
    """GET /gallery/list - List galleries with preview images.

    Unauthenticated and unquota'd, so the work one request can ask for has to
    be bounded by the request itself. Clamped exactly as /prompts/recent and
    /prompts/history clamp, so the three endpoints are visibly consistent.

    The clamp bounds the per-folder fan-out below; ``_list_gallery_page``
    bounds the listing that feeds it. Both are needed -- clamping only the
    fan-out still left every public request paging the whole ``sessions/``
    prefix, because S3 returns it ascending and the newest page is last.
    """
    params = event.get("queryStringParameters") or {}
    try:
        limit = max(1, min(int(params.get("limit", 20)), 50))
    except (ValueError, TypeError):
        return response(400, {"error": "Invalid limit parameter"})
    cursor = params.get("cursor") or None
    # Validated here rather than ignored downstream. A cursor the index cannot
    # parse would otherwise query from the top and answer "page 7" with page 1
    # plus a fresh cursor, which an infinite-scroll client renders as the
    # newest galleries repeating below the older ones, forever.
    if cursor is not None and not image_storage.validate_gallery_id(cursor):
        return response(400, {"error": "Invalid cursor parameter"})

    try:
        # One folder more than asked for. That extra name is how the response
        # knows whether a next page exists without a second read, and it is
        # dropped before anything is expanded.
        gallery_folders = _list_gallery_page(limit + 1, cursor, correlation_id)
        has_more = len(gallery_folders) > limit
        # Slice BEFORE the fan-out. This is the whole finding: each surviving
        # folder costs its own paginating LIST, and expanding folders that
        # will not be returned is what made an unauthenticated GET cost O(N)
        # with N growing with every session ever created.
        gallery_folders = gallery_folders[:limit]

        def _build_gallery_entry(folder):
            images = image_storage.list_gallery_images(folder)
            if not images:
                # The index outliving its images is expected, not exceptional:
                # S3's lifecycle deletes the objects on a schedule and DynamoDB
                # reaps the matching index entry lazily, so there is always a
                # window where a folder is indexed and empty. Returning it
                # would render a blank tile, which the S3-derived listing could
                # never produce because S3 was the source of truth for both
                # existence and content. Dropped rather than surfaced.
                return None

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
                entry = future.result()
                if entry is not None:
                    galleries.append(entry)
            except Exception as e:
                StructuredLogger.warning(
                    f"Failed to load gallery {futures[future]}: {e}",
                    correlation_id=correlation_id,
                )

        # Sort by ID (timestamp) descending. list_galleries already returns
        # them that way; as_completed does not preserve submission order.
        galleries.sort(key=lambda g: g["id"], reverse=True)

        body: dict[str, Any] = {"galleries": galleries, "total": len(galleries)}
        if has_more and gallery_folders:
            # The oldest id this page ASKED for, not the oldest that survived
            # expansion. The two differ whenever a per-folder LIST throws, and
            # deriving the boundary from the survivors is wrong in both
            # directions: a failure in the middle of the page leaves a folder
            # newer than the cursor and therefore excluded from every later
            # page, while a failure at the tail moves the cursor forward and
            # re-serves folders the caller already has.
            #
            # Anchoring to the requested slice makes the boundary independent
            # of which expansions happened to succeed: no duplicates, and the
            # only loss is a folder missing from the run in which its LIST
            # failed. `dropped` reports that rather than letting `total`
            # quietly under-count.
            body["nextCursor"] = gallery_folders[-1]
        dropped = len(gallery_folders) - len(galleries)
        if dropped:
            body["dropped"] = dropped
        return response(200, body)

    except ValueError as e:
        # An unparseable cursor that got past validate_gallery_id.
        StructuredLogger.warning(
            f"Rejected gallery cursor: {e}",
            correlation_id=correlation_id,
        )
        return response(400, {"error": "Invalid cursor parameter"})
    except Exception as e:
        StructuredLogger.error(
            f"Error in handle_gallery_list: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        # 503, not a fallback to listing S3. This endpoint is unauthenticated
        # and unquota'd, and the index exists precisely so a public GET cannot
        # be made to walk the whole bucket. Falling back on failure would hand
        # that back to anyone who could make DynamoDB fail, for every request,
        # for the duration of the outage. A retryable error keeps the bound.
        return response(503, {"error": "Gallery temporarily unavailable", "retryAfter": 30})


def handle_log_endpoint(event: LambdaEvent) -> ApiResponse:
    """POST /log - Accept frontend error logs."""
    raw_body = event.get("body", "")
    if len(raw_body) > MAX_LOG_BODY_SIZE:
        return response(413, {"error": "Request body too large"})

    # Per-request size was already bounded; this bounds the rate. CloudWatch
    # ingestion is billed and the log is where an incident gets diagnosed, so
    # an unmetered writer buys both cost and cover. Checked before the record
    # is written, or it bounds nothing.
    limited = _public_ip_rate_limited(
        event, "log", config.log_ip_limit, config.log_ip_window_seconds
    )
    if limited:
        return limited

    try:
        body = json.loads(raw_body or "{}")
        ip = event.get("requestContext", {}).get("http", {}).get("sourceIp", "unknown")

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
            session, _resolve_tier_or_none(event)
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
    item = _user_repo.touch_quota_window(
        ctx.user_id,
        window_seconds,
        int(time.time()),
        daily_window_seconds=config.paid_window_seconds,
    )
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

    A thin wrapper over ``utils.http.json_response`` -- the header policy,
    including the ``Retry-After`` mirroring and the rule that a wildcard
    origin never carries credentials, lives there so admin and billing
    responses get exactly the same treatment. Kept as a name because ~60 call
    sites in this module use it and renaming them would bury this change.
    """
    return json_response(status_code, body, set_cookie)
