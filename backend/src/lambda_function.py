"""
Main Lambda handler for Pixel Prompt v2.
Routes API requests to appropriate handlers for image generation,
iteration, outpainting, and session status.
"""

import json
import random
import re
import traceback
from datetime import datetime, timezone
from uuid import uuid4
import boto3

# Import configuration
from config import (
    s3_bucket, cloudfront_domain,
    global_limit, ip_limit, ip_include,
    get_enabled_models, get_model, get_model_config_dict,
    MODELS, MAX_ITERATIONS, ITERATION_WARNING_THRESHOLD,
)

# Import modules
from jobs.manager import SessionManager
from models.handlers import get_handler, get_iterate_handler, get_outpaint_handler
from models.context import ContextManager, create_context_entry
from utils.storage import ImageStorage
from utils.rate_limit import RateLimiter
from utils.content_filter import ContentFilter
from api.enhance import PromptEnhancer
from api.log import handle_log
from utils.logger import StructuredLogger
from utils import error_responses

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


def extract_correlation_id(event):
    """Extract correlation ID from event headers or generate new one."""
    headers = event.get('headers', {})
    correlation_id = headers.get('x-correlation-id') or headers.get('X-Correlation-ID')
    return correlation_id or str(uuid4())


def lambda_handler(event, context):
    """Main Lambda handler function."""
    correlation_id = extract_correlation_id(event)

    path = event.get('rawPath', event.get('path', ''))
    # Remove stage prefix (len('/Prod/') = 6, len('/Staging/') = 9)
    if path.startswith('/Prod/'):
        path = path[6:]
    elif path.startswith('/Staging/'):
        path = path[9:]
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
        StructuredLogger.error(f"Error in lambda_handler: {str(e)}", correlation_id=correlation_id)
        traceback.print_exc()
        return response(500, {'error': 'Internal server error'})


def handle_generate(event, correlation_id=None):
    """
    POST /generate - Create new session and generate initial images.

    Request body:
        {"prompt": "text prompt", "ip": "client IP"}

    Returns:
        {"sessionId": "uuid", "models": {...}}
    """
    try:
        body = json.loads(event.get('body', '{}'))
        prompt = body.get('prompt', '')

        # Prefer real client IP from API Gateway, fall back to body.ip for local dev
        ip = event.get('requestContext', {}).get('http', {}).get('sourceIp') or body.get('ip', 'unknown')

        # Validate
        if not prompt:
            return response(400, error_responses.prompt_required())
        if len(prompt) > 1000:
            return response(400, error_responses.prompt_too_long(max_length=1000))

        # Rate limit
        if rate_limiter.check_rate_limit(ip):
            return response(429, error_responses.rate_limit_exceeded(retry_after=3600))

        # Content filter
        if content_filter.check_prompt(prompt):
            return response(400, error_responses.inappropriate_content())

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

        # Generate initial images for all enabled models in parallel
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = {}
        target = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H-%M-%S')

        def generate_for_model(model_config):
            model_name = model_config.name
            start_time = time.time()

            try:
                # Add iteration 0
                iteration_index = session_manager.add_iteration(
                    session_id, model_name, prompt
                )

                # Get handler and generate
                handler = get_handler(model_config.provider)
                config_dict = get_model_config_dict(model_config)
                result = handler(config_dict, prompt, {})

                duration = time.time() - start_time

                if result['status'] == 'success':
                    # Upload image
                    image_key = image_storage.upload_image(
                        result['image'],
                        target,
                        model_name,
                        prompt,
                        iteration=iteration_index
                    )

                    # Complete iteration
                    session_manager.complete_iteration(
                        session_id, model_name, iteration_index, image_key, duration
                    )

                    # Add to context
                    entry = create_context_entry(iteration_index, prompt, image_key)
                    context_manager.add_entry(session_id, model_name, entry)

                    return model_name, {
                        'status': 'completed',
                        'imageKey': image_key,
                        'imageUrl': image_storage.get_cloudfront_url(image_key),
                        'iteration': iteration_index,
                        'duration': duration
                    }
                else:
                    session_manager.fail_iteration(
                        session_id, model_name, iteration_index, result.get('error', 'Unknown error')
                    )
                    return model_name, {
                        'status': 'error',
                        'error': result.get('error', 'Unknown error'),
                        'iteration': iteration_index
                    }

            except Exception as e:
                return model_name, {'status': 'error', 'error': str(e)}

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(generate_for_model, model): model
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

    except json.JSONDecodeError:
        return response(400, error_responses.invalid_json())
    except Exception as e:
        StructuredLogger.error(f"Error in handle_generate: {str(e)}", correlation_id=correlation_id)
        traceback.print_exc()
        return response(500, error_responses.internal_server_error())


def handle_iterate(event, correlation_id=None):
    """
    POST /iterate - Iterate on existing image with new prompt.

    Request body:
        {
            "sessionId": "uuid",
            "model": "flux|recraft|gemini|openai",
            "prompt": "refinement instruction"
        }

    Returns:
        {"status": "completed|error", "imageKey": "...", ...}
    """
    try:
        body = json.loads(event.get('body', '{}'))
        session_id = body.get('sessionId')
        model_name = body.get('model')
        prompt = body.get('prompt', '')

        # Extract IP for rate limiting
        # Prefer real client IP from API Gateway, fall back to body.ip for local dev
        ip = event.get('requestContext', {}).get('http', {}).get('sourceIp') or body.get('ip', 'unknown')

        # Rate limit check
        if rate_limiter.check_rate_limit(ip):
            return response(429, error_responses.rate_limit_exceeded(retry_after=3600))

        # Validate
        if not session_id:
            return response(400, {'error': 'sessionId is required'})
        if not model_name:
            return response(400, {'error': 'model is required'})
        if not prompt:
            return response(400, error_responses.prompt_required())

        if model_name not in MODELS:
            return response(400, {'error': f'Invalid model: {model_name}'})

        # Content filter
        if content_filter.check_prompt(prompt):
            return response(400, error_responses.inappropriate_content())

        # Get model config
        try:
            model_config = get_model(model_name)
        except ValueError as e:
            return response(400, {'error': str(e)})

        # Check iteration count
        iteration_count = session_manager.get_iteration_count(session_id, model_name)

        # Warning at threshold
        warning = None
        if iteration_count >= ITERATION_WARNING_THRESHOLD:
            remaining = MAX_ITERATIONS - iteration_count
            warning = f'Only {remaining} iterations remaining for {model_name}'

        if iteration_count >= MAX_ITERATIONS:
            return response(400, {
                'error': f'Iteration limit ({MAX_ITERATIONS}) reached for {model_name}'
            })

        # Get previous image
        source_image_key = session_manager.get_latest_image_key(session_id, model_name)
        if not source_image_key:
            return response(400, {'error': f'No source image for {model_name}'})

        # Load source image
        source_data = image_storage.get_image(source_image_key)
        if not source_data or not source_data.get('output'):
            return response(500, {'error': 'Failed to load source image'})

        source_image = source_data['output']  # base64

        # Get context
        context = context_manager.get_context_for_iteration(session_id, model_name)

        import time
        start_time = time.time()

        # Add iteration
        iteration_index = session_manager.add_iteration(session_id, model_name, prompt)

        # Get iterate handler
        iterate_handler = get_iterate_handler(model_config.provider)
        config_dict = get_model_config_dict(model_config)

        # Execute iteration
        result = iterate_handler(config_dict, source_image, prompt, context)

        duration = time.time() - start_time
        target = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H-%M-%S')

        if result['status'] == 'success':
            # Upload new image
            image_key = image_storage.upload_image(
                result['image'],
                target,
                model_name,
                prompt,
                iteration=iteration_index
            )

            # Complete iteration
            session_manager.complete_iteration(
                session_id, model_name, iteration_index, image_key, duration
            )

            # Add to context
            entry = create_context_entry(iteration_index, prompt, image_key)
            context_manager.add_entry(session_id, model_name, entry)

            resp = {
                'status': 'completed',
                'imageKey': image_key,
                'imageUrl': image_storage.get_cloudfront_url(image_key),
                'iteration': iteration_index,
                'iterationCount': iteration_index + 1,
                'duration': duration
            }
            if warning:
                resp['warning'] = warning

            return response(200, resp)
        else:
            session_manager.fail_iteration(
                session_id, model_name, iteration_index, result.get('error', 'Unknown error')
            )
            return response(500, {
                'status': 'error',
                'error': result.get('error', 'Unknown error'),
                'iteration': iteration_index
            })

    except json.JSONDecodeError:
        return response(400, error_responses.invalid_json())
    except Exception as e:
        StructuredLogger.error(f"Error in handle_iterate: {str(e)}", correlation_id=correlation_id)
        traceback.print_exc()
        return response(500, error_responses.internal_server_error())


def handle_outpaint(event, correlation_id=None):
    """
    POST /outpaint - Expand image to new aspect ratio.

    Request body:
        {
            "sessionId": "uuid",
            "model": "flux|recraft|gemini|openai",
            "preset": "16:9|9:16|1:1|4:3|expand_all",
            "prompt": "description for expanded areas"
        }

    Returns:
        {"status": "completed|error", "imageKey": "...", ...}
    """
    try:
        body = json.loads(event.get('body', '{}'))
        session_id = body.get('sessionId')
        model_name = body.get('model')
        preset = body.get('preset')
        prompt = body.get('prompt', 'continue the scene naturally')

        # Extract IP for rate limiting
        # Prefer real client IP from API Gateway, fall back to body.ip for local dev
        ip = event.get('requestContext', {}).get('http', {}).get('sourceIp') or body.get('ip', 'unknown')

        # Rate limit check
        if rate_limiter.check_rate_limit(ip):
            return response(429, error_responses.rate_limit_exceeded(retry_after=3600))

        # Validate
        if not session_id:
            return response(400, {'error': 'sessionId is required'})
        if not model_name:
            return response(400, {'error': 'model is required'})
        if not preset:
            return response(400, {'error': 'preset is required'})

        valid_presets = ['16:9', '9:16', '1:1', '4:3', 'expand_all']
        if preset not in valid_presets:
            return response(400, {'error': f'Invalid preset. Valid: {valid_presets}'})

        if model_name not in MODELS:
            return response(400, {'error': f'Invalid model: {model_name}'})

        # Content filter
        if content_filter.check_prompt(prompt):
            return response(400, error_responses.inappropriate_content())

        # Get model config
        try:
            model_config = get_model(model_name)
        except ValueError as e:
            return response(400, {'error': str(e)})

        # Check iteration count (outpaint counts as iteration)
        iteration_count = session_manager.get_iteration_count(session_id, model_name)
        if iteration_count >= MAX_ITERATIONS:
            return response(400, {
                'error': f'Iteration limit ({MAX_ITERATIONS}) reached for {model_name}'
            })

        # Get source image
        source_image_key = session_manager.get_latest_image_key(session_id, model_name)
        if not source_image_key:
            return response(400, {'error': f'No source image for {model_name}'})

        source_data = image_storage.get_image(source_image_key)
        if not source_data or not source_data.get('output'):
            return response(500, {'error': 'Failed to load source image'})

        source_image = source_data['output']  # base64

        import time
        start_time = time.time()

        # Add iteration (outpaint)
        iteration_index = session_manager.add_iteration(
            session_id, model_name, prompt,
            is_outpaint=True, outpaint_preset=preset
        )

        # Get outpaint handler
        outpaint_handler = get_outpaint_handler(model_config.provider)
        config_dict = get_model_config_dict(model_config)

        # Execute outpaint
        result = outpaint_handler(config_dict, source_image, preset, prompt)

        duration = time.time() - start_time
        target = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H-%M-%S')

        if result['status'] == 'success':
            # Upload new image
            image_key = image_storage.upload_image(
                result['image'],
                target,
                model_name,
                f"outpaint:{preset} - {prompt}",
                iteration=iteration_index
            )

            # Complete iteration
            session_manager.complete_iteration(
                session_id, model_name, iteration_index, image_key, duration
            )

            # Add to context
            entry = create_context_entry(iteration_index, f"outpaint:{preset}", image_key)
            context_manager.add_entry(session_id, model_name, entry)

            return response(200, {
                'status': 'completed',
                'imageKey': image_key,
                'imageUrl': image_storage.get_cloudfront_url(image_key),
                'iteration': iteration_index,
                'iterationCount': iteration_index + 1,
                'preset': preset,
                'duration': duration
            })
        else:
            session_manager.fail_iteration(
                session_id, model_name, iteration_index, result.get('error', 'Unknown error')
            )
            return response(500, {
                'status': 'error',
                'error': result.get('error', 'Unknown error'),
                'iteration': iteration_index
            })

    except json.JSONDecodeError:
        return response(400, error_responses.invalid_json())
    except Exception as e:
        StructuredLogger.error(f"Error in handle_outpaint: {str(e)}", correlation_id=correlation_id)
        traceback.print_exc()
        return response(500, error_responses.internal_server_error())


def handle_status(event, correlation_id=None):
    """
    GET /status/{sessionId} - Get session status and results.

    Returns session status with all model states and iterations.
    """
    try:
        path = event.get('rawPath', event.get('path', ''))
        session_id = path.split('/')[-1]

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
        StructuredLogger.error(f"Error in handle_status: {str(e)}", correlation_id=correlation_id)
        traceback.print_exc()
        return response(500, error_responses.internal_server_error())


def handle_enhance(event, correlation_id=None):
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
        StructuredLogger.error(f"Error in handle_enhance: {str(e)}", correlation_id=correlation_id)
        traceback.print_exc()
        return response(500, error_responses.internal_server_error())


def handle_gallery_list(event, correlation_id=None):
    """GET /gallery/list - List all galleries with preview images."""
    try:
        gallery_folders = image_storage.list_galleries()

        galleries = []
        for folder in gallery_folders:
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

            galleries.append({
                'id': folder,
                'timestamp': timestamp_str,
                'previewData': preview_data,
                'imageCount': len(images)
            })

        return response(200, {'galleries': galleries, 'total': len(galleries)})

    except Exception:
        traceback.print_exc()
        return response(500, {'error': 'Internal server error'})


def handle_log_endpoint(event):
    """POST /log - Accept frontend error logs."""
    try:
        body = json.loads(event.get('body', '{}'))
        ip = event.get('requestContext', {}).get('http', {}).get('sourceIp', 'unknown')

        if rate_limiter.check_rate_limit(ip):
            return response(429, {'error': 'Rate limit exceeded'})

        headers = event.get('headers', {})
        correlation_id = headers.get('x-correlation-id') or headers.get('X-Correlation-ID')

        result = handle_log(body, correlation_id, ip)
        return response(200, result)

    except json.JSONDecodeError:
        return response(400, {'error': 'Invalid JSON in request body'})
    except Exception:
        traceback.print_exc()
        return response(500, {'error': 'Internal server error'})


def handle_gallery_detail(event, correlation_id=None):
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

        images = []
        for key in image_keys:
            metadata = image_storage.get_image(key)
            if metadata:
                images.append({
                    'key': key,
                    'url': image_storage.get_cloudfront_url(key),
                    'model': metadata.get('model', 'Unknown'),
                    'prompt': metadata.get('prompt', ''),
                    'timestamp': metadata.get('timestamp'),
                    'output': metadata.get('output')
                })

        return response(200, {
            'galleryId': gallery_id,
            'images': images,
            'total': len(images)
        })

    except Exception:
        traceback.print_exc()
        return response(500, {'error': 'Internal server error'})


def response(status_code, body):
    """Helper function to create API Gateway response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With, X-Correlation-ID'
        },
        'body': json.dumps(body)
    }
