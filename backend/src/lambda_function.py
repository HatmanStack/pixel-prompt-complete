"""
Main Lambda handler for Pixel Prompt Complete.
Routes API requests to appropriate handlers for image generation,
status checking, and prompt enhancement.
"""

import json
import traceback
from datetime import datetime, timezone
import boto3
import threading

# Import configuration
from config import (
    models, s3_bucket, cloudfront_domain,
    global_limit, ip_limit, ip_include
)

# Import modules
from models.registry import ModelRegistry
from jobs.manager import JobManager
from jobs.executor import JobExecutor
from utils.storage import ImageStorage
from utils.rate_limit import RateLimiter
from utils.content_filter import ContentFilter
from api.enhance import PromptEnhancer
from api.log import handle_log
from utils.logger import StructuredLogger
from utils import error_responses
from uuid import uuid4

# Initialize components at module level (Lambda container reuse)
print("Initializing Lambda components...")

# S3 client
s3_client = boto3.client('s3')

# Model registry
model_registry = ModelRegistry()

# Job manager
job_manager = JobManager(s3_client, s3_bucket)

# Image storage
image_storage = ImageStorage(s3_client, s3_bucket, cloudfront_domain)

# Rate limiter
rate_limiter = RateLimiter(s3_client, s3_bucket, global_limit, ip_limit, ip_include)

# Content filter
content_filter = ContentFilter()

# Job executor
job_executor = JobExecutor(job_manager, image_storage, model_registry)

# Prompt enhancer
prompt_enhancer = PromptEnhancer(model_registry)

print(f"Lambda initialization complete: {model_registry.get_model_count()} models configured")


def extract_correlation_id(event):
    """
    Extract correlation ID from event headers.
    Generates new UUID if not provided.

    Args:
        event: API Gateway event object

    Returns:
        str: Correlation ID
    """
    headers = event.get('headers', {})
    correlation_id = headers.get('x-correlation-id') or headers.get('X-Correlation-ID')

    if not correlation_id:
        correlation_id = str(uuid4())

    return correlation_id


def lambda_handler(event, context):
    """
    Main Lambda handler function.
    Routes requests to appropriate handlers based on path and method.

    Args:
        event: API Gateway event object
        context: Lambda context object

    Returns:
        API Gateway response object with status code and body
    """
    # Extract correlation ID from headers
    correlation_id = extract_correlation_id(event)

    # Extract path and method from API Gateway event
    path = event.get('rawPath', event.get('path', ''))
    method = event.get('requestContext', {}).get('http', {}).get('method',
             event.get('httpMethod', ''))

    # Log request with correlation ID
    StructuredLogger.info(f"Request: {method} {path}", correlation_id=correlation_id)

    try:
        # Route based on path and method
        if path == '/generate' and method == 'POST':
            return handle_generate(event, correlation_id)
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
    POST /generate - Create image generation job.

    Request body:
        {
            "prompt": "text prompt",
            "steps": 25,
            "guidance": 7,
            "control": 1.0,
            "ip": "client IP address"
        }

    Returns:
        {"jobId": "uuid-v4-string"}
    """
    try:
        body = json.loads(event.get('body', '{}'))

        prompt = body.get('prompt', '')
        steps = body.get('steps', 25)
        guidance = body.get('guidance', 7)
        control = body.get('control', 1.0)

        # Get client IP
        ip = body.get('ip')
        if not ip:
            # Try to extract from event
            ip = event.get('requestContext', {}).get('http', {}).get('sourceIp', 'unknown')

        # Validate input
        if not prompt or len(prompt) == 0:
            return response(400, error_responses.prompt_required())

        if len(prompt) > 1000:
            return response(400, error_responses.prompt_too_long(max_length=1000))

        # Check rate limit
        is_limited = rate_limiter.check_rate_limit(ip)
        if is_limited:
            # Calculate retry after (rate limiter uses 1 hour window for global limit)
            return response(429, error_responses.rate_limit_exceeded(
                retry_after=3600,  # 1 hour in seconds
                limit_type="requests"
            ))

        # Check content filter
        is_blocked = content_filter.check_prompt(prompt)
        if is_blocked:
            return response(400, error_responses.inappropriate_content())

        # Build parameters
        params = {
            'steps': steps,
            'guidance': guidance,
            'control': control
        }

        # Create target timestamp for grouping images
        target = datetime.now(timezone.utc).strftime('%Y-%m-%d-%H-%M-%S')

        # Create job
        job_id = job_manager.create_job(
            prompt=prompt,
            params=params,
            models=model_registry.get_all_models()
        )

        # Start background execution in separate thread
        # This allows Lambda to return immediately while processing continues
        #
        # WARNING: This pattern has limitations in Lambda environment:
        # - Lambda may freeze/terminate the container after handler returns
        # - Background threads may not complete if container is terminated
        # - Job status is saved to S3, so partial results are preserved
        # - For production, consider: Step Functions, SQS, or synchronous execution
        # - This works for MVP due to Lambda container reuse and S3 persistence
        thread = threading.Thread(
            target=job_executor.execute_job,
            args=(job_id, prompt, params, target)
        )
        thread.daemon = True
        thread.start()

        StructuredLogger.info(
            f"Job {job_id} created and started in background",
            correlation_id=correlation_id,
            jobId=job_id,
            prompt=prompt[:100]  # Log first 100 chars of prompt
        )

        # Return job ID immediately
        return response(200, {
            'jobId': job_id,
            'message': 'Job created successfully',
            'totalModels': model_registry.get_model_count()
        })

    except json.JSONDecodeError:
        StructuredLogger.error("Invalid JSON in request body", correlation_id=correlation_id)
        return response(400, error_responses.invalid_json())
    except Exception as e:
        StructuredLogger.error(f"Error in handle_generate: {str(e)}", correlation_id=correlation_id)
        traceback.print_exc()
        return response(500, error_responses.internal_server_error())


def handle_status(event, correlation_id=None):
    """
    GET /status/{jobId} - Get job status and results.

    Path parameters:
        jobId: UUID of the job

    Returns:
        Job status object with completion progress
    """
    try:
        path_parameters = event.get('pathParameters', {})
        job_id = path_parameters.get('jobId', 'unknown')

        # Get job status from S3
        status = job_manager.get_job_status(job_id)

        if not status:
            return response(404, error_responses.job_not_found(job_id))

        # Add CloudFront URLs to image results
        for result in status.get('results', []):
            if result.get('status') == 'completed' and result.get('imageKey'):
                result['imageUrl'] = image_storage.get_cloudfront_url(result['imageKey'])

        return response(200, status)

    except Exception as e:
        StructuredLogger.error(f"Error in handle_status: {str(e)}", correlation_id=correlation_id)
        traceback.print_exc()
        return response(500, error_responses.internal_server_error())


def handle_enhance(event, correlation_id=None):
    """
    POST /enhance - Enhance prompt using configured LLM.

    Request body:
        {
            "prompt": "short prompt"
        }

    Returns:
        {
            "enhanced": "detailed expanded prompt"
        }
    """
    try:
        body = json.loads(event.get('body', '{}'))
        prompt = body.get('prompt', '')

        # Validate input
        if not prompt or len(prompt) == 0:
            return response(400, error_responses.prompt_required())

        if len(prompt) > 500:
            return response(400, error_responses.prompt_too_long(max_length=500))

        # Check content filter
        is_blocked = content_filter.check_prompt(prompt)
        if is_blocked:
            return response(400, error_responses.inappropriate_content())

        # Enhance prompt
        enhanced = prompt_enhancer.enhance_safe(prompt)

        return response(200, {
            'original': prompt,
            'enhanced': enhanced
        })

    except json.JSONDecodeError:
        return response(400, error_responses.invalid_json())
    except Exception as e:
        StructuredLogger.error(f"Error in handle_enhance: {str(e)}", correlation_id=correlation_id)
        traceback.print_exc()
        return response(500, error_responses.internal_server_error())


def handle_gallery_list(event, correlation_id=None):
    """
    GET /gallery/list - List all galleries with preview images.

    Returns:
        {
            "galleries": [
                {
                    "id": "2025-11-15-14-30-45",
                    "timestamp": "2025-11-15T14:30:45Z",
                    "preview": "https://cloudfront.../preview.json"
                }
            ]
        }
    """
    try:
        # Get list of gallery folders
        gallery_folders = image_storage.list_galleries()
        StructuredLogger.info(f"Listing {len(gallery_folders)} galleries", correlation_id=correlation_id)

        # Build response with preview images
        galleries = []
        for folder in gallery_folders:
            # Get first image from each gallery as preview
            images = image_storage.list_gallery_images(folder)

            preview_url = None
            if images:
                # Use first image as preview
                preview_key = images[0]
                preview_url = image_storage.get_cloudfront_url(preview_key)

            # Parse timestamp from folder name (format: YYYY-MM-DD-HH-MM-SS)
            try:
                timestamp_str = f"{folder[:10]}T{folder[11:13]}:{folder[14:16]}:{folder[17:19]}Z"
            except (IndexError, ValueError):
                timestamp_str = folder

            galleries.append({
                'id': folder,
                'timestamp': timestamp_str,
                'preview': preview_url,
                'imageCount': len(images)
            })

        print(f"Returning {len(galleries)} galleries")

        return response(200, {
            'galleries': galleries,
            'total': len(galleries)
        })

    except Exception as e:
        print(f"Error in handle_gallery_list: {str(e)}")
        traceback.print_exc()
        return response(500, {'error': 'Internal server error'})


def handle_log_endpoint(event):
    """
    POST /log - Accept frontend error logs and write to CloudWatch.

    Request body:
        {
            "level": "ERROR|WARNING|INFO|DEBUG",
            "message": "error message",
            "stack": "error stack trace (optional)",
            "metadata": {"key": "value"} (optional)
        }

    Headers:
        X-Correlation-ID: UUID for request tracing

    Returns:
        {"success": true, "message": "Log received successfully"}
    """
    try:
        body = json.loads(event.get('body', '{}'))

        # Get client IP
        ip = event.get('requestContext', {}).get('http', {}).get('sourceIp', 'unknown')

        # Check rate limit (lower limit for logging to prevent spam)
        # Using 100 logs per hour per IP
        is_limited = rate_limiter.check_rate_limit(ip)
        if is_limited:
            return response(429, {
                'error': 'Rate limit exceeded',
                'message': 'Too many log requests. Please try again later.'
            })

        # Extract correlation ID from headers
        headers = event.get('headers', {})
        correlation_id = headers.get('x-correlation-id') or headers.get('X-Correlation-ID')

        # Handle log
        result = handle_log(body, correlation_id, ip)

        return response(200, result)

    except json.JSONDecodeError:
        return response(400, {'error': 'Invalid JSON in request body'})
    except ValueError as e:
        return response(400, {'error': str(e)})
    except Exception as e:
        print(f"Error in handle_log_endpoint: {str(e)}")
        traceback.print_exc()
        return response(500, {'error': 'Internal server error'})


def handle_gallery_detail(event, correlation_id=None):
    """
    GET /gallery/{galleryId} - Get all images from a specific gallery.

    Returns:
        {
            "galleryId": "2025-11-15-14-30-45",
            "images": [
                {
                    "key": "group-images/...",
                    "url": "https://cloudfront.../...",
                    "model": "DALL-E 3",
                    "prompt": "...",
                    "timestamp": "..."
                }
            ]
        }
    """
    try:
        # Extract gallery ID from path
        path = event.get('rawPath', event.get('path', ''))
        gallery_id = path.split('/')[-1]
        StructuredLogger.info(f"Fetching gallery: {gallery_id}", correlation_id=correlation_id)

        if not gallery_id or gallery_id == 'list':
            return response(400, {'error': 'Gallery ID is required'})

        # Get all images from gallery
        image_keys = image_storage.list_gallery_images(gallery_id)

        # Fetch metadata for each image
        images = []
        for key in image_keys:
            metadata = image_storage.get_image(key)
            if metadata:
                images.append({
                    'key': key,
                    'url': image_storage.get_cloudfront_url(key),
                    'model': metadata.get('model', 'Unknown'),
                    'prompt': metadata.get('prompt', ''),
                    'steps': metadata.get('steps'),
                    'guidance': metadata.get('guidance'),
                    'control': metadata.get('control'),
                    'timestamp': metadata.get('timestamp'),
                    'output': metadata.get('output')  # Include base64 image data
                })

        print(f"Returning {len(images)} images from gallery {gallery_id}")

        return response(200, {
            'galleryId': gallery_id,
            'images': images,
            'total': len(images)
        })

    except Exception as e:
        print(f"Error in handle_gallery_detail: {str(e)}")
        traceback.print_exc()
        return response(500, {'error': 'Internal server error'})


def response(status_code, body):
    """
    Helper function to create API Gateway response.

    Args:
        status_code: HTTP status code
        body: Response body (dict)

    Returns:
        API Gateway response object
    """
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
