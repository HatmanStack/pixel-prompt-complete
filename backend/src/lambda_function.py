"""
Main Lambda handler for Pixel Prompt v2.
Routes API requests to appropriate handlers for image generation,
iteration, outpainting, and session status.
"""

import json
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import boto3

import config
from api.enhance import PromptEnhancer
from api.log import handle_log
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
from ops.model_counters import ModelCounterService
from users.quota import enforce_quota
from users.repository import UserRepository
from users.tier import TierContext, resolve_tier
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

# Content filter
content_filter = ContentFilter()

# Prompt enhancer
prompt_enhancer = PromptEnhancer()

# Module-level thread pools for Lambda container reuse.
# Separate pools prevent gallery metadata fetches from starving generation threads.
_executor = ThreadPoolExecutor(max_workers=generate_thread_workers)
_gallery_executor = ThreadPoolExecutor(max_workers=4)


@dataclass
class ValidatedRequest:
    """Result of successful request validation."""

    body: dict[str, Any]
    ip: str
    prompt: str
    tier: TierContext | None = None


def _anon_tier() -> TierContext:
    return TierContext(
        tier="paid",
        user_id="anon",
        email=None,
        is_authenticated=False,
        guest_token_id=None,
        issue_guest_cookie=False,
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

    ``endpoint_kind`` is one of ``"generate"``, ``"refine"``, or ``"none"``
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
        tier_ctx = _anon_tier()

    # CAPTCHA verification for guest /generate requests
    if config.captcha_enabled and tier_ctx.tier == "guest" and endpoint_kind == "generate":
        captcha_token = body.get("captchaToken")
        if not captcha_token:
            return None, response(403, error_responses.captcha_required())
        from ops.captcha import verify_turnstile

        if not verify_turnstile(captcha_token, ip):
            return None, response(403, error_responses.captcha_failed())

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

    # Quota enforcement (after validation so invalid requests don't consume quota)
    if endpoint_kind in ("generate", "refine") and config.auth_enabled:
        # Guests blocked from refine immediately (no auth).
        if tier_ctx.tier == "guest" and endpoint_kind == "refine":
            return None, response(402, error_responses.auth_required())
        result = enforce_quota(tier_ctx, endpoint_kind, _user_repo, int(time.time()))
        if not result.allowed:
            if result.reason == "suspended":
                return None, response(403, error_responses.account_suspended())
            if result.reason == "guest_global":
                return None, response(429, error_responses.guest_global_limit())
            return None, response(
                429,
                error_responses.tier_quota_exceeded(tier_ctx.tier, result.reset_at),
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
    context_prompt: str | None = None,
) -> dict[str, Any]:
    """Handle a successful handler result: upload, complete iteration, add context.

    Args:
        context_prompt: Prompt string to store in context. Defaults to ``prompt``.

    Returns:
        Dict with image_key and image_url.
    """
    image_key = image_storage.upload_image(
        result["image"],
        target,
        model_name,
        prompt,
        iteration=iteration_index,
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


def _not_implemented(endpoint: str) -> ApiResponse:
    """Stub response for routes whose business logic lands in later phases."""
    return response(501, {"error": f"{endpoint} not implemented"})


def lambda_handler(event: LambdaEvent, context: LambdaContext) -> ApiResponse:
    """Main Lambda handler function."""
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
        elif path == "/enhance" and method == "POST":
            return handle_enhance(event, correlation_id)
        elif path == "/log" and method == "POST":
            return handle_log_endpoint(event)
        elif path == "/gallery/list" and method == "GET":
            return handle_gallery_list(event, correlation_id)
        elif path.startswith("/gallery/") and method == "GET":
            return handle_gallery_detail(event, correlation_id)
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
        else:
            return response(404, {"error": "Not found", "path": path, "method": method})

    except Exception as e:
        StructuredLogger.error(
            f"Error in lambda_handler: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, {"error": "Internal server error"})


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
            return response(500, {"error": "No models enabled"})

        # Filter models by per-model cost ceiling (only when auth is enabled)
        models_to_dispatch = []
        skipped_models = {}
        if config.auth_enabled:
            now_ts = int(time.time())
            for model in enabled_models:
                if _model_counter_service.check_model_allowed(model.name, now_ts):
                    models_to_dispatch.append(model)
                else:
                    skipped_models[model.name] = {
                        "status": "skipped",
                        "reason": "daily_cap_reached",
                    }
        else:
            models_to_dispatch = list(enabled_models)

        if not models_to_dispatch:
            return response(429, error_responses.model_cost_ceiling())

        enabled_model_names = [m.name for m in models_to_dispatch]

        # Create session
        session_id = session_manager.create_session(prompt, enabled_model_names)

        StructuredLogger.info(
            f"Session {session_id} created",
            correlation_id=correlation_id,
            sessionId=session_id,
            models=enabled_model_names,
        )

        results = {}
        target = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")

        def generate_for_model(model_config):
            model_name = model_config.name
            start_time = time.time()
            iteration_index = None

            try:
                iteration_index = session_manager.add_iteration(session_id, model_name, prompt)

                handler = get_handler(model_config.provider)
                config_dict = get_model_config_dict(model_config)
                result = handler(config_dict, prompt, {})

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
                    except Exception:
                        pass  # Best-effort; don't mask the original error
                return model_name, {"status": "error", "error": sanitized}

        # Include skipped models in results
        results.update(skipped_models)

        # Execute in parallel using module-level executor
        futures = {
            _executor.submit(generate_for_model, model): model for model in models_to_dispatch
        }
        for future in as_completed(futures):
            model_name, result = future.result()
            results[model_name] = result

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
        return response(
            200,
            {"sessionId": session_id, "prompt": prompt, "models": results},
            set_cookie=set_cookie,
        )

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
) -> tuple[tuple[str, int] | None, ApiResponse | None]:
    """Check iteration limit, load source image from latest iteration.

    Returns:
        ((source_image_base64, iteration_count), None) on success,
        or (None, error_response) on failure.
    """
    # Single S3 read: load session once and derive iteration count + image key
    session = session_manager.get_session(session_id)
    if not session:
        return None, response(404, {"error": f"Session {session_id} not found"})

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

    source_data = image_storage.get_image(source_image_key)
    if not source_data or not source_data.get("output"):
        return None, response(500, {"error": "Failed to load source image"})

    return (source_data["output"], iteration_count), None


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
    try:
        refs, err = _validate_refinement_request(validated)
        if err:
            return err
        session_id, model_name, model_config = refs

        loaded, err = _load_source_image(session_id, model_name)
        if err:
            return err
        source_image, iteration_count = loaded

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

        if result["status"] == "success":
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
            except Exception:
                pass  # Best-effort; don't mask the original error
        StructuredLogger.error(
            f"Error in {handler_name}: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
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
        endpoint_kind="refine",
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

        # Add CloudFront URLs to all completed iterations
        for model_name, model_data in session.get("models", {}).items():
            for iteration in model_data.get("iterations", []):
                if iteration.get("status") == "completed" and iteration.get("imageKey"):
                    iteration["imageUrl"] = image_storage.get_cloudfront_url(iteration["imageKey"])

        return response(200, session)

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
        endpoint_kind="none",
    )
    if err:
        return err

    try:
        enhanced = prompt_enhancer.enhance_safe(validated.prompt)

        return response(
            200, {"original": validated.prompt, "short_prompt": enhanced, "long_prompt": enhanced}
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
            if images:
                preview_url = image_storage.get_cloudfront_url(images[0])

            try:
                timestamp_str = f"{folder[:10]}T{folder[11:13]}:{folder[14:16]}:{folder[17:19]}Z"
            except (IndexError, ValueError):
                timestamp_str = folder

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

    return response(
        200,
        {
            "userId": ctx.user_id,
            "email": ctx.email,
            "tier": ctx.tier,
            "quota": quota,
            "billing": billing,
        },
    )


def response(
    status_code: int,
    body: dict[str, Any],
    set_cookie: str | None = None,
) -> ApiResponse:
    """Helper function to create API Gateway response."""
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": cors_allowed_origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, X-Correlation-ID",
    }
    resp: ApiResponse = {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body),
    }
    if set_cookie:
        resp["cookies"] = [set_cookie]
    return resp
