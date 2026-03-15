"""
Main Lambda handler for Pixel Prompt v2.
Routes API requests to appropriate handlers for image generation,
iteration, outpainting, and session status.
"""

import json
import random
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

import boto3

from api.enhance import PromptEnhancer
from api.log import handle_log
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
    global_limit,
    ip_include,
    ip_limit,
    s3_bucket,
)
from jobs.manager import SessionManager
from models.context import ContextManager, create_context_entry
from models.handlers import (
    get_handler,
    get_iterate_handler,
    get_outpaint_handler,
    sanitize_error_message,
)
from utils import error_responses
from utils.content_filter import ContentFilter
from utils.logger import StructuredLogger
from utils.rate_limit import RateLimiter
from utils.storage import ImageStorage

# Type aliases for Lambda events and responses
LambdaEvent = Dict[str, Any]
LambdaContext = Any  # AWS Lambda context object
ApiResponse = Dict[str, Any]

# Request body size limits
MAX_BODY_SIZE = 1_048_576  # 1 MB for generation endpoints
MAX_LOG_BODY_SIZE = 10_240  # 10 KB for log endpoint

# Reserved metadata keys that must not be overwritten by client log payloads
_RESERVED_LOG_METADATA_KEYS = frozenset({
    'timestamp', 'level', 'correlation_id', 'message',
})

# Initialize components at module level (Lambda container reuse)
s3_client = boto3.client('s3')

# Session manager (replaces job manager)
session_manager = SessionManager(s3_client, s3_bucket)

# Context manager for iteration history
context_manager = ContextManager(s3_client, s3_bucket)

# Image storage
image_storage = ImageStorage(s3_client, s3_bucket, cloudfront_domain)

# Rate limiter
rate_limiter = RateLimiter(s3_client, s3_bucket, global_limit, ip_limit, ip_include)

# Content filter
content_filter = ContentFilter()

# Prompt enhancer
prompt_enhancer = PromptEnhancer()

# Module-level thread pool for Lambda container reuse
_executor = ThreadPoolExecutor(max_workers=generate_thread_workers)


@dataclass
class ValidatedRequest:
    """Result of successful request validation."""
    body: dict[str, Any]
    ip: str
    prompt: str


def _parse_and_validate_request(
    event: LambdaEvent,
    require_prompt: bool = True,
    default_prompt: str = '',
    max_body_size: int = MAX_BODY_SIZE,
) -> tuple[ValidatedRequest | None, ApiResponse | None]:
    """Shared request validation for POST handlers.

    Performs: body size check, JSON parsing, IP extraction, rate limiting,
    prompt validation, and content filtering.

    Returns:
        (ValidatedRequest, None) on success, or (None, error_response) on failure.
    """
    raw_body = event.get('body', '')
    if len(raw_body) > max_body_size:
        return None, response(413, {'error': 'Request body too large'})

    try:
        body = json.loads(raw_body or '{}')
    except json.JSONDecodeError:
        return None, response(400, error_responses.invalid_json())

    # Prefer real client IP from API Gateway, fall back to body.ip for local dev
    ip = (
        event.get('requestContext', {}).get('http', {}).get('sourceIp')
        or body.get('ip', 'unknown')
    )

    # Rate limit
    if rate_limiter.check_rate_limit(ip):
        return None, response(429, error_responses.rate_limit_exceeded(retry_after=3600))

    # Extract prompt
    prompt = body.get('prompt', default_prompt)

    if require_prompt:
        if not prompt:
            return None, response(400, error_responses.prompt_required())
        if len(prompt) > 1000:
            return None, response(400, error_responses.prompt_too_long(max_length=1000))

    # Content filter
    if prompt and content_filter.check_prompt(prompt):
        return None, response(400, error_responses.inappropriate_content())

    return ValidatedRequest(body=body, ip=ip, prompt=prompt), None


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
        result['image'],
        target,
        model_name,
        prompt,
        iteration=iteration_index,
    )

    session_manager.complete_iteration(
        session_id, model_name, iteration_index, image_key, duration,
    )

    entry = create_context_entry(iteration_index, context_prompt or prompt, image_key)
    context_manager.add_entry(session_id, model_name, entry)

    return {
        'image_key': image_key,
        'image_url': image_storage.get_cloudfront_url(image_key),
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
    headers = event.get('headers', {}) or {}
    correlation_id = headers.get('x-correlation-id') or headers.get('X-Correlation-ID')
    return correlation_id or str(uuid4())


def lambda_handler(event: LambdaEvent, context: LambdaContext) -> ApiResponse:
    """Main Lambda handler function."""
    correlation_id = extract_correlation_id(event)

    path = event.get('rawPath', event.get('path', ''))
    # Remove known stage prefixes (e.g. /Prod/generate -> /generate)
    for stage_prefix in ('/Prod/', '/Staging/', '/Dev/'):
        if path.startswith(stage_prefix):
            path = path[len(stage_prefix):]
            break
    # Ensure path starts with /
    if path and not path.startswith('/'):
        path = '/' + path

    method = event.get('requestContext', {}).get('http', {}).get('method',
             event.get('httpMethod', ''))

    StructuredLogger.info(f"Request: {method} {path}", correlation_id=correlation_id)

    if method == 'OPTIONS':
        return response(200, {'message': 'CORS preflight'})

    try:
        # Route based on path and method
        if path == '/generate' and method == 'POST':
            return handle_generate(event, correlation_id)
        elif path == '/iterate' and method == 'POST':
            return handle_iterate(event, correlation_id)
        elif path == '/outpaint' and method == 'POST':
            return handle_outpaint(event, correlation_id)
        elif path.startswith('/status/') and method == 'GET':
            return handle_status(event, correlation_id)
        elif path == '/enhance' and method == 'POST':
            return handle_enhance(event, correlation_id)
        elif path == '/log' and method == 'POST':
            return handle_log_endpoint(event)
        elif path == '/gallery/list' and method == 'GET':
            return handle_gallery_list(event, correlation_id)
        elif path.startswith('/gallery/') and method == 'GET':
            return handle_gallery_detail(event, correlation_id)
        else:
            return response(404, {'error': 'Not found', 'path': path, 'method': method})

    except Exception as e:
        StructuredLogger.error(
            f"Error in lambda_handler: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, {'error': 'Internal server error'})


def handle_generate(event: LambdaEvent, correlation_id: Optional[str] = None) -> ApiResponse:
    """
    POST /generate - Create new session and generate initial images.

    Request body:
        {"prompt": "text prompt", "ip": "client IP"}

    Returns:
        {"sessionId": "uuid", "models": {...}}
    """
    validated, err = _parse_and_validate_request(event, require_prompt=True)
    if err:
        return err

    try:
        prompt = validated.prompt

        # Get enabled models
        enabled_models = get_enabled_models()
        if not enabled_models:
            return response(500, {'error': 'No models enabled'})

        enabled_model_names = [m.name for m in enabled_models]

        # Create session
        session_id = session_manager.create_session(prompt, enabled_model_names)

        StructuredLogger.info(
            f"Session {session_id} created",
            correlation_id=correlation_id,
            sessionId=session_id,
            models=enabled_model_names
        )

        results = {}
        target = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H-%M-%S')

        def generate_for_model(model_config):
            model_name = model_config.name
            start_time = time.time()
            iteration_index = None

            try:
                iteration_index = session_manager.add_iteration(
                    session_id, model_name, prompt
                )

                handler = get_handler(model_config.provider)
                config_dict = get_model_config_dict(model_config)
                result = handler(config_dict, prompt, {})

                duration = time.time() - start_time

                if result['status'] == 'success':
                    info = _handle_successful_result(
                        session_id, model_name, prompt, result,
                        iteration_index, target, duration,
                    )
                    return model_name, {
                        'status': 'completed',
                        'imageKey': info['image_key'],
                        'imageUrl': info['image_url'],
                        'iteration': iteration_index,
                        'duration': duration,
                    }
                else:
                    error_msg = result.get('error', 'Unknown error')
                    _handle_failed_result(session_id, model_name, iteration_index, error_msg)
                    return model_name, {
                        'status': 'error',
                        'error': error_msg,
                        'iteration': iteration_index,
                    }

            except Exception as e:
                sanitized = sanitize_error_message(e)
                if iteration_index is not None:
                    try:
                        _handle_failed_result(
                            session_id, model_name, iteration_index, sanitized
                        )
                    except Exception:
                        pass  # Best-effort; don't mask the original error
                return model_name, {'status': 'error', 'error': sanitized}

        # Execute in parallel using module-level executor
        futures = {
            _executor.submit(generate_for_model, model): model
            for model in enabled_models
        }
        for future in as_completed(futures):
            model_name, result = future.result()
            results[model_name] = result

        return response(200, {
            'sessionId': session_id,
            'prompt': prompt,
            'models': results
        })

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
    session_id = body.get('sessionId')
    model_name = body.get('model')

    if not session_id:
        return None, response(400, {'error': 'sessionId is required'})
    if not model_name:
        return None, response(400, {'error': 'model is required'})
    if model_name not in MODELS:
        return None, response(400, {'error': f'Invalid model: {model_name}'})

    try:
        model_config = get_model(model_name)
    except ValueError as e:
        return None, response(400, {'error': str(e)})

    return (session_id, model_name, model_config), None


def _load_source_image(
    session_id: str, model_name: str,
) -> tuple[str | None, ApiResponse | None]:
    """Check iteration limit, load source image from latest iteration.

    Returns:
        (source_image_base64, None) on success, or (None, error_response) on failure.
    """
    iteration_count = session_manager.get_iteration_count(session_id, model_name)
    if iteration_count >= MAX_ITERATIONS:
        return None, response(400, {
            'error': f'Iteration limit ({MAX_ITERATIONS}) reached for {model_name}',
        })

    source_image_key = session_manager.get_latest_image_key(session_id, model_name)
    if not source_image_key:
        return None, response(400, {'error': f'No source image for {model_name}'})

    source_data = image_storage.get_image(source_image_key)
    if not source_data or not source_data.get('output'):
        return None, response(500, {'error': 'Failed to load source image'})

    return source_data['output'], None


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
    try:
        refs, err = _validate_refinement_request(validated)
        if err:
            return err
        session_id, model_name, model_config = refs

        source_image, err = _load_source_image(session_id, model_name)
        if err:
            return err

        # Iteration warning at threshold
        iteration_count = session_manager.get_iteration_count(session_id, model_name)
        warning = None
        if iteration_count >= ITERATION_WARNING_THRESHOLD:
            remaining = MAX_ITERATIONS - iteration_count
            warning = f'Only {remaining} iterations remaining for {model_name}'

        prompt = validated.prompt
        start_time = time.time()

        iter_kwargs = add_iteration_kwargs or {}
        iteration_index = session_manager.add_iteration(
            session_id, model_name, prompt, **iter_kwargs,
        )

        config_dict = get_model_config_dict(model_config)
        handler = get_handler_fn(model_config.provider)
        handler_args = build_handler_args_fn(
            config_dict, source_image, prompt, session_id, model_name,
        )
        result = handler(*handler_args)

        duration = time.time() - start_time
        target = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H-%M-%S')

        if result['status'] == 'success':
            store_prompt = result_prompt_fn(prompt) if result_prompt_fn else prompt
            ctx_prompt = context_prompt_fn(prompt) if context_prompt_fn else None
            info = _handle_successful_result(
                session_id, model_name, store_prompt, result,
                iteration_index, target, duration,
                context_prompt=ctx_prompt,
            )
            resp = {
                'status': 'completed',
                'imageKey': info['image_key'],
                'imageUrl': info['image_url'],
                'iteration': iteration_index,
                'iterationCount': iteration_index + 1,
                'duration': duration,
            }
            if warning:
                resp['warning'] = warning
            if extra_response_fields:
                resp.update(extra_response_fields)
            return response(200, resp)
        else:
            error_msg = result.get('error', 'Unknown error')
            _handle_failed_result(session_id, model_name, iteration_index, error_msg)
            return response(500, {
                'status': 'error', 'error': error_msg, 'iteration': iteration_index,
            })

    except Exception as e:
        StructuredLogger.error(
            f"Error in {handler_name}: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, error_responses.internal_server_error())


def handle_iterate(event: LambdaEvent, correlation_id: Optional[str] = None) -> ApiResponse:
    """POST /iterate - Iterate on existing image with new prompt."""
    validated, err = _parse_and_validate_request(event, require_prompt=True)
    if err:
        return err

    def _build_args(config_dict, source_image, prompt, session_id, model_name):
        context = context_manager.get_context_for_iteration(session_id, model_name)
        return (config_dict, source_image, prompt, context)

    return _handle_refinement(
        validated, correlation_id, 'handle_iterate',
        get_handler_fn=get_iterate_handler,
        build_handler_args_fn=_build_args,
    )


def handle_outpaint(event: LambdaEvent, correlation_id: Optional[str] = None) -> ApiResponse:
    """POST /outpaint - Expand image to new aspect ratio."""
    validated, err = _parse_and_validate_request(
        event, require_prompt=False, default_prompt='continue the scene naturally',
    )
    if err:
        return err

    preset = validated.body.get('preset')
    if not preset:
        return response(400, {'error': 'preset is required'})
    valid_presets = ['16:9', '9:16', '1:1', '4:3', 'expand_all']
    if preset not in valid_presets:
        return response(400, {'error': f'Invalid preset. Valid: {valid_presets}'})

    def _build_args(config_dict, source_image, prompt, session_id, model_name):
        return (config_dict, source_image, preset, prompt)

    return _handle_refinement(
        validated, correlation_id, 'handle_outpaint',
        get_handler_fn=get_outpaint_handler,
        build_handler_args_fn=_build_args,
        add_iteration_kwargs={'is_outpaint': True, 'outpaint_preset': preset},
        result_prompt_fn=lambda p: f"outpaint:{preset} - {p}",
        context_prompt_fn=lambda p: f"outpaint:{preset}",
        extra_response_fields={'preset': preset},
    )


def handle_status(event: LambdaEvent, correlation_id: Optional[str] = None) -> ApiResponse:
    """
    GET /status/{sessionId} - Get session status and results.

    Returns session status with all model states and iterations.
    """
    try:
        path = event.get('rawPath', event.get('path', ''))
        session_id = path.split('/')[-1]

        # Validate session_id format (alphanumeric + hyphens, max 64 chars)
        if not session_id or not re.match(r'^[a-zA-Z0-9\-]{1,64}$', session_id):
            return response(400, {'error': 'Invalid session ID format'})

        session = session_manager.get_session(session_id)
        if not session:
            return response(404, {'error': f'Session {session_id} not found'})

        # Add CloudFront URLs to all completed iterations
        for model_name, model_data in session.get('models', {}).items():
            for iteration in model_data.get('iterations', []):
                if iteration.get('status') == 'completed' and iteration.get('imageKey'):
                    iteration['imageUrl'] = image_storage.get_cloudfront_url(iteration['imageKey'])

        return response(200, session)

    except Exception as e:
        StructuredLogger.error(
            f"Error in handle_status: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, error_responses.internal_server_error())


def handle_enhance(event: LambdaEvent, correlation_id: Optional[str] = None) -> ApiResponse:
    """POST /enhance - Enhance prompt using configured LLM."""
    try:
        body = json.loads(event.get('body', '{}'))
        prompt = body.get('prompt', '')

        if not prompt:
            return response(400, error_responses.prompt_required())
        if len(prompt) > 500:
            return response(400, error_responses.prompt_too_long(max_length=500))

        if content_filter.check_prompt(prompt):
            return response(400, error_responses.inappropriate_content())

        enhanced = prompt_enhancer.enhance_safe(prompt)

        return response(200, {
            'original': prompt,
            'short_prompt': enhanced,
            'long_prompt': enhanced
        })

    except json.JSONDecodeError:
        return response(400, error_responses.invalid_json())
    except Exception as e:
        StructuredLogger.error(
            f"Error in handle_enhance: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, error_responses.internal_server_error())


def handle_gallery_list(event: LambdaEvent, correlation_id: Optional[str] = None) -> ApiResponse:
    """GET /gallery/list - List all galleries with preview images."""
    try:
        gallery_folders = image_storage.list_galleries()

        def _build_gallery_entry(folder):
            all_images = image_storage.list_gallery_images(folder)
            thumbnails = [img for img in all_images if '-thumb.json' in img]
            images = [img for img in all_images if '-thumb.json' not in img]

            preview_data = None
            if thumbnails:
                thumbnail_key = random.choice(thumbnails)
                thumbnail_metadata = image_storage.get_image(thumbnail_key)
                if thumbnail_metadata and thumbnail_metadata.get('output'):
                    preview_data = thumbnail_metadata['output']

            try:
                timestamp_str = f"{folder[:10]}T{folder[11:13]}:{folder[14:16]}:{folder[17:19]}Z"
            except (IndexError, ValueError):
                timestamp_str = folder

            return {
                'id': folder,
                'timestamp': timestamp_str,
                'previewData': preview_data,
                'imageCount': len(images),
            }

        # Fetch gallery entries in parallel
        galleries = []
        futures = {_executor.submit(_build_gallery_entry, f): f for f in gallery_folders}
        for future in as_completed(futures):
            try:
                galleries.append(future.result())
            except Exception as e:
                StructuredLogger.warning(
                    f"Failed to load gallery {futures[future]}: {e}",
                    correlation_id=correlation_id,
                )

        # Sort by ID (timestamp) descending
        galleries.sort(key=lambda g: g['id'], reverse=True)

        return response(200, {'galleries': galleries, 'total': len(galleries)})

    except Exception as e:
        StructuredLogger.error(
            f"Error in handle_gallery_list: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, {'error': 'Internal server error'})


def handle_log_endpoint(event: LambdaEvent) -> ApiResponse:
    """POST /log - Accept frontend error logs."""
    raw_body = event.get('body', '')
    if len(raw_body) > MAX_LOG_BODY_SIZE:
        return response(413, {'error': 'Request body too large'})

    try:
        body = json.loads(raw_body or '{}')
        ip = event.get('requestContext', {}).get('http', {}).get('sourceIp', 'unknown')

        if rate_limiter.check_rate_limit(ip):
            return response(429, {'error': 'Rate limit exceeded'})

        # Sanitize metadata: remove reserved keys that could overwrite structured log fields
        if 'metadata' in body and isinstance(body['metadata'], dict):
            body['metadata'] = {
                k: v for k, v in body['metadata'].items()
                if k not in _RESERVED_LOG_METADATA_KEYS
            }

        headers = event.get('headers', {})
        correlation_id = headers.get('x-correlation-id') or headers.get('X-Correlation-ID')

        result = handle_log(body, correlation_id, ip)
        return response(200, result)

    except json.JSONDecodeError:
        return response(400, {'error': 'Invalid JSON in request body'})
    except Exception as e:
        StructuredLogger.error(
            f"Error in handle_log_endpoint: {e}",
            traceback=traceback.format_exc(),
        )
        return response(500, {'error': 'Internal server error'})


def handle_gallery_detail(event: LambdaEvent, correlation_id: Optional[str] = None) -> ApiResponse:
    """GET /gallery/{galleryId} - Get all images from a specific gallery."""
    try:
        path = event.get('rawPath', event.get('path', ''))
        gallery_id = path.split('/')[-1]

        if not gallery_id or gallery_id == 'list':
            return response(400, {'error': 'Gallery ID is required'})

        if not re.match(r'^[a-zA-Z0-9\-]+$', gallery_id):
            return response(400, {'error': 'Invalid gallery ID format'})

        if '..' in gallery_id or '/' in gallery_id or '\\' in gallery_id:
            return response(400, {'error': 'Invalid gallery ID'})

        image_keys = image_storage.list_gallery_images(gallery_id)

        def _load_image(key):
            metadata = image_storage.get_image(key)
            if metadata:
                return {
                    'key': key,
                    'url': image_storage.get_cloudfront_url(key),
                    'model': metadata.get('model', 'Unknown'),
                    'prompt': metadata.get('prompt', ''),
                    'timestamp': metadata.get('timestamp'),
                    'output': metadata.get('output'),
                }
            return None

        # Fetch image metadata in parallel
        images = []
        futures = {_executor.submit(_load_image, key): key for key in image_keys}
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

        return response(200, {
            'galleryId': gallery_id,
            'images': images,
            'total': len(images),
        })

    except Exception as e:
        StructuredLogger.error(
            f"Error in handle_gallery_detail: {e}",
            correlation_id=correlation_id,
            traceback=traceback.format_exc(),
        )
        return response(500, {'error': 'Internal server error'})


def response(status_code: int, body: Dict[str, Any]) -> ApiResponse:
    """Helper function to create API Gateway response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': cors_allowed_origin,
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With, X-Correlation-ID'
        },
        'body': json.dumps(body)
    }
