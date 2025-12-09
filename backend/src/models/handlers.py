"""
Provider-specific handlers for AI image generation.

Each handler implements image generation for a specific AI provider,
returning a standardized response format.

Security Note: API keys are injected via SAM parameter overrides at deploy time
from .env.deploy (not committed to repo) and stored in Lambda environment variables.
This is the standard AWS pattern for secrets management. Keys never appear in
client-side code. The sanitize_error_message() function provides defense-in-depth
by redacting any keys that might appear in exception messages returned to clients.
"""

import base64
import json
import re
import requests
import time
import warnings
from typing import Dict, Callable
from openai import OpenAI
import boto3
from google import genai
from google.genai import types


def sanitize_error_message(error: Exception) -> str:
    """
    Sanitize error messages to remove sensitive information like API keys.

    Args:
        error: Exception object

    Returns:
        Sanitized error message string
    """
    error_str = str(error)

    # Remove potential API keys (common patterns)
    # Bearer tokens
    error_str = re.sub(r'Bearer\s+[A-Za-z0-9\-_\.]+', 'Bearer [REDACTED]', error_str)
    # API keys in various formats
    error_str = re.sub(r'(api[_-]?key|apikey|key|token|secret|password|authorization)["\']?\s*[:=]\s*["\']?[A-Za-z0-9\-_\.]+["\']?', r'\1=[REDACTED]', error_str, flags=re.IGNORECASE)
    # sk- prefixed keys (OpenAI style)
    error_str = re.sub(r'sk-[A-Za-z0-9\-_]{20,}', '[REDACTED_KEY]', error_str)
    # Generic long alphanumeric strings that look like keys (32+ chars)
    error_str = re.sub(r'[A-Za-z0-9]{32,}', '[REDACTED]', error_str)

    return error_str


def handle_openai(model_config: Dict, prompt: str, _params: Dict) -> Dict:
    """
    Handle image generation for OpenAI (DALL-E 2/3 and gpt-image-1).

    Args:
        model_config: Model configuration dict with 'id' and 'api_key'
        prompt: Text prompt for image generation
        _params: Generation parameters (unused - uses default settings)

    Returns:
        Standardized response dict with status and image data
    """
    try:
        model_id = model_config["id"]

        # Initialize OpenAI client with timeout
        client = OpenAI(api_key=model_config.get('api_key') or None, timeout=120.0)

        # gpt-image-1 uses different parameters and returns base64 directly
        if model_id == "gpt-image-1":
            response = client.images.generate(
                model=model_id,
                prompt=prompt,
                size="1024x1024",
                quality="medium",
            )

            # Validate response structure
            if not response.data or len(response.data) == 0:
                raise ValueError("OpenAI returned empty data array")

            # gpt-image-1 returns base64 directly
            image_base64 = response.data[0].b64_json

        else:
            # DALL-E 2/3 returns URLs
            response = client.images.generate(
                model=model_id,
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )

            # Validate response structure
            if not response.data or len(response.data) == 0:
                raise ValueError("OpenAI returned empty data array")

            # Extract image URL from response
            image_url = response.data[0].url

            # Download image
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()

            # Convert to base64
            image_base64 = base64.b64encode(img_response.content).decode('utf-8')

        return {
            'status': 'success',
            'image': image_base64,
            'model': model_id,
            'provider': 'openai'
        }

    except requests.Timeout:
        error_msg = "Image download timeout after 30 seconds"
        return {
            'status': 'error',
            'error': error_msg,
            'model': model_config['id'],
            'provider': 'openai'
        }

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config['id'],
            'provider': 'openai'
        }


def handle_google_gemini(model_config: Dict, prompt: str, _params: Dict) -> Dict:
    """
    Handle image generation for Google Gemini 2.0.

    Args:
        model_config: Model configuration dict with 'name' and 'key'
        prompt: Text prompt for image generation
        _params: Generation parameters (unused - Gemini uses default settings)

    Returns:
        Standardized response dict
    """
    try:

        # Create Gemini client
        client = genai.Client(api_key=model_config.get('api_key') or None)

        # Generate image with multimodal model
        response = client.models.generate_content(
            model=model_config["id"],
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=['Text', 'Image']
            )
        )

        # Validate response structure
        if not response.candidates or len(response.candidates) == 0:
            raise ValueError("Gemini returned empty candidates array")

        # Extract inline image data from response parts
        image_data = None
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'inline_data') and part.inline_data:
                image_data = part.inline_data.data
                break

        if not image_data:
            raise ValueError("No image data found in Gemini response")

        # Convert bytes to base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')


        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config['id'],
            'provider': 'google_gemini'
        }

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config['id'],
            'provider': 'google_gemini'
        }


def handle_google_imagen(model_config: Dict, prompt: str, _params: Dict) -> Dict:
    """
    Handle image generation for Google Imagen 3.0.

    Args:
        model_config: Model configuration dict
        prompt: Text prompt for image generation
        _params: Generation parameters (unused - Imagen uses default settings)

    Returns:
        Standardized response dict
    """
    try:

        # Create Imagen client
        client = genai.Client(api_key=model_config.get('api_key') or None)

        # Generate image
        response = client.models.generate_images(
            model='imagen-3.0-generate-002',
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1
            )
        )

        # Validate response structure
        if not response.generated_images or len(response.generated_images) == 0:
            raise ValueError("Imagen returned empty generated_images array")

        # Extract image bytes from generated_images
        image_bytes = response.generated_images[0].image.image_bytes

        # Convert bytes directly to base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')


        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config['id'],
            'provider': 'google_imagen'
        }

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config['id'],
            'provider': 'google_imagen'
        }


def handle_bedrock_nova(model_config: Dict, prompt: str, params: Dict) -> Dict:
    """
    Handle image generation for AWS Bedrock Nova Canvas.

    Args:
        model_config: Model configuration dict
        prompt: Text prompt for image generation
        params: Generation parameters

    Returns:
        Standardized response dict
    """
    try:

        # Create boto3 session with credentials
        # Note: AWS credentials should be in environment or Lambda execution role
        bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name='us-east-1'  # Nova Canvas requires us-east-1
        )

        # Build request body for Nova Canvas
        request_body = {
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                "text": prompt
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": 1024,
                "width": 1024,
                "cfgScale": params.get('guidance', 8.0),
                "seed": 0
            }
        }

        # Invoke model
        response = bedrock.invoke_model(
            modelId=model_config['id'],
            body=json.dumps(request_body)
        )

        # Parse response
        response_body = json.loads(response['body'].read())

        # Validate response structure
        if 'images' not in response_body or len(response_body['images']) == 0:
            raise ValueError("Bedrock Nova returned empty images array")

        # Extract base64 image from response
        image_base64 = response_body['images'][0]


        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config['id'],
            'provider': 'bedrock_nova'
        }

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config['id'],
            'provider': 'bedrock_nova'
        }


def handle_bedrock_sd(model_config: Dict, prompt: str, params: Dict) -> Dict:
    """
    Handle image generation for AWS Bedrock Stable Diffusion.

    Args:
        model_config: Model configuration dict
        prompt: Text prompt for image generation
        params: Generation parameters

    Returns:
        Standardized response dict
    """
    try:

        # Create boto3 client
        bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name='us-west-2'  # Stable Diffusion requires us-west-2
        )

        # Build request body for Stable Diffusion
        request_body = {
            "prompt": prompt,
            "mode": "text-to-image",
            "aspect_ratio": "1:1",
            "output_format": "png",
            "seed": 0
        }

        # Add negative prompt if provided
        negative_prompt = params.get('negative_prompt', '')
        if negative_prompt:
            request_body['negative_prompt'] = negative_prompt

        # Invoke model
        response = bedrock.invoke_model(
            modelId=model_config['id'],
            body=json.dumps(request_body)
        )

        # Parse response
        response_body = json.loads(response['body'].read())

        # Validate response structure
        if 'images' not in response_body or len(response_body['images']) == 0:
            raise ValueError("Bedrock SD returned empty images array")

        # Extract base64 image from response
        image_base64 = response_body['images'][0]


        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config['id'],
            'provider': 'bedrock_sd'
        }

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config['id'],
            'provider': 'bedrock_sd'
        }


def handle_stability(model_config: Dict, prompt: str, params: Dict) -> Dict:
    """
    Handle image generation for Stability AI.

    Args:
        model_config: Model configuration dict
        prompt: Text prompt for image generation
        params: Generation parameters

    Returns:
        Standardized response dict
    """
    try:

        # Stability AI API endpoint
        url = "https://api.stability.ai/v2beta/stable-image/generate/sd3"

        # Headers
        headers = {
            "authorization": f"Bearer {model_config.get('api_key') or None}",
            "accept": "image/*"
        }

        # Build multipart form data
        files = {
            'prompt': (None, prompt),
            'model': (None, 'sd3-large-turbo'),
            'output_format': (None, 'png'),
            'aspect_ratio': (None, '1:1')
        }

        # Add negative prompt if provided
        negative_prompt = params.get('negative_prompt', '')
        if negative_prompt:
            files['negative_prompt'] = (None, negative_prompt)

        # Make request
        response = requests.post(url, headers=headers, files=files, timeout=60)
        response.raise_for_status()

        # Response is raw image bytes - convert to base64
        image_base64 = base64.b64encode(response.content).decode('utf-8')


        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config['id'],
            'provider': 'stability'
        }

    except requests.Timeout:
        error_msg = "Stability AI request timeout after 60 seconds"
        return {
            'status': 'error',
            'error': error_msg,
            'model': model_config['id'],
            'provider': 'stability'
        }

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config['id'],
            'provider': 'stability'
        }


def handle_bfl(model_config: Dict, prompt: str, params: Dict) -> Dict:
    """
    Handle image generation for Black Forest Labs (Flux).

    Args:
        model_config: Model configuration dict
        prompt: Text prompt for image generation
        params: Generation parameters (supports max_poll_attempts, poll_interval_seconds)

    Returns:
        Standardized response dict
    """
    try:
        # Use model ID directly as endpoint (e.g., "flux-pro-1.1", "flux-dev")
        endpoint = model_config['id']


        # Start job
        start_url = f"https://api.bfl.ai/v1/{endpoint}"
        headers = {
            "x-key": model_config.get('api_key') or None,
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": prompt,
            "width": 1024,
            "height": 1024
        }

        response = requests.post(start_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        job_data = response.json()
        job_id = job_data.get('id')

        if not job_id:
            raise ValueError("No job ID returned from BFL API")


        # Poll for result (tunable via params)
        result_url = f"https://api.bfl.ai/v1/get_result?id={job_id}"
        max_attempts = params.get('max_poll_attempts', 40)  # Default: 40 attempts
        poll_interval = params.get('poll_interval_seconds', 3)  # Default: 3 seconds
        attempt = 0

        while attempt < max_attempts:
            time.sleep(poll_interval)
            attempt += 1

            result_response = requests.get(result_url, headers=headers, timeout=10)
            result_response.raise_for_status()
            result_data = result_response.json()

            status = result_data.get('status')

            if status == 'Ready':
                # Download image from result URL
                image_url = result_data['result']['sample']
                img_response = requests.get(image_url, timeout=30)
                img_response.raise_for_status()

                # Convert to base64
                image_base64 = base64.b64encode(img_response.content).decode('utf-8')


                return {
                    'status': 'success',
                    'image': image_base64,
                    'model': model_config['id'],
                    'provider': 'bfl'
                }

            elif status == 'Error':
                error_msg = result_data.get('error', 'Unknown error')
                raise ValueError(f"BFL job failed: {error_msg}")

        # Timeout
        raise TimeoutError(f"BFL job timeout after {max_attempts * 3} seconds")

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config['id'],
            'provider': 'bfl'
        }


def handle_recraft(model_config: Dict, prompt: str, _params: Dict) -> Dict:
    """
    Handle image generation for Recraft.

    Args:
        model_config: Model configuration dict
        prompt: Text prompt for image generation
        _params: Generation parameters (unused - Recraft uses default settings)

    Returns:
        Standardized response dict
    """
    try:

        # Recraft uses OpenAI-compatible API with custom base URL
        client = OpenAI(
            api_key=model_config.get('api_key') or None,
            base_url="https://external.api.recraft.ai/v1"
        )

        # Call image generation (OpenAI-compatible)
        response = client.images.generate(
            model="recraftv3",
            prompt=prompt,
            size="1024x1024",
            n=1
        )

        # Extract image URL
        image_url = response.data[0].url

        # Download image
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()

        # Convert to base64
        image_base64 = base64.b64encode(img_response.content).decode('utf-8')


        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config['id'],
            'provider': 'recraft'
        }

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config['id'],
            'provider': 'recraft'
        }


def handle_generic(model_config: Dict, prompt: str, _params: Dict) -> Dict:
    """
    Generic fallback handler for unknown providers.

    Attempts to call as OpenAI-compatible API.

    Args:
        model_config: Model configuration dict
        prompt: Text prompt for image generation
        _params: Generation parameters (unused - generic handler uses defaults)

    Returns:
        Standardized response dict
    """
    try:

        # Try as OpenAI-compatible API
        # Use the model name as-is
        client_kwargs = {
            'api_key': model_config.get('api_key') or None,
            'timeout': 120.0
        }

        # Support custom base_url for OpenAI-compatible providers
        if 'base_url' in model_config:
            client_kwargs['base_url'] = model_config['base_url']

        client = OpenAI(**client_kwargs)

        response = client.images.generate(
            model=model_config['id'],
            prompt=prompt,
            size="1024x1024",
            n=1
        )

        # Validate response structure
        if not response.data or len(response.data) == 0:
            raise ValueError("Generic handler returned empty data array")

        # Extract image URL
        image_url = response.data[0].url

        # Download image
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()

        # Convert to base64
        image_base64 = base64.b64encode(img_response.content).decode('utf-8')


        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config['id'],
            'provider': 'generic'
        }

    except Exception as e:
        error_msg = f"Generic handler failed (model may not be OpenAI-compatible): {sanitize_error_message(e)}"
        return {
            'status': 'error',
            'error': error_msg,
            'model': model_config['id'],
            'provider': 'generic'
        }


def get_handler(provider: str) -> Callable:
    """
    Get the appropriate handler function for a provider.

    Args:
        provider: Provider identifier (e.g., 'openai', 'google_gemini')

    Returns:
        Handler function for the provider
    """
    handlers = {
        'openai': handle_openai,
        'google_gemini': handle_google_gemini,
        'google_imagen': handle_google_imagen,
        'bedrock_nova': handle_bedrock_nova,
        'bedrock_sd': handle_bedrock_sd,
        'stability': handle_stability,
        'bfl': handle_bfl,
        'recraft': handle_recraft,
        'generic': handle_generic
    }

    handler = handlers.get(provider, handle_generic)
    if provider not in handlers:
        warnings.warn(f"Unknown provider '{provider}', falling back to generic handler")

    return handler


# ============================================================================
# ITERATION HANDLERS
# ============================================================================

def iterate_flux(model_config: Dict, source_image: bytes, prompt: str, context: list) -> Dict:
    """
    Iterate on an image using FLUX Fill API.

    Uses full-image mask for complete refinement based on prompt.

    Args:
        model_config: Model configuration with API key
        source_image: Base64-encoded source image
        prompt: Refinement instruction
        context: Rolling 3-iteration context window (unused for Flux)

    Returns:
        Standardized response dict
    """
    try:
        # BFL Fill endpoint for image editing
        url = "https://api.bfl.ai/v1/flux-pro-1.1-fill"
        headers = {
            "x-key": model_config.get('api_key', ''),
            "Content-Type": "application/json"
        }

        # Build context prompt from history
        context_prompt = prompt
        if context:
            history = " | ".join([c['prompt'] for c in context[-2:]])
            context_prompt = f"Previous: {history}. Now: {prompt}"

        payload = {
            "image": source_image if isinstance(source_image, str) else base64.b64encode(source_image).decode('utf-8'),
            "prompt": context_prompt,
            "width": 1024,
            "height": 1024
        }

        # Start job
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        job_data = response.json()
        job_id = job_data.get('id')

        if not job_id:
            raise ValueError("No job ID returned from BFL Fill API")

        # Poll for result
        result_url = f"https://api.bfl.ai/v1/get_result?id={job_id}"
        for attempt in range(40):
            time.sleep(3)
            result_response = requests.get(result_url, headers=headers, timeout=10)
            result_response.raise_for_status()
            result_data = result_response.json()

            if result_data.get('status') == 'Ready':
                image_url = result_data['result']['sample']
                img_response = requests.get(image_url, timeout=30)
                img_response.raise_for_status()
                image_base64 = base64.b64encode(img_response.content).decode('utf-8')

                return {
                    'status': 'success',
                    'image': image_base64,
                    'model': model_config.get('id', 'flux-pro-1.1'),
                    'provider': 'bfl'
                }

            elif result_data.get('status') == 'Error':
                raise ValueError(f"BFL Fill job failed: {result_data.get('error', 'Unknown error')}")

        raise TimeoutError("BFL Fill job timeout after 120 seconds")

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config.get('id', 'flux'),
            'provider': 'bfl'
        }


def iterate_recraft(model_config: Dict, source_image: bytes, prompt: str, context: list) -> Dict:
    """
    Iterate on an image using Recraft imageToImage endpoint.

    Args:
        model_config: Model configuration with API key
        source_image: Base64-encoded source image
        prompt: Refinement instruction
        context: Rolling 3-iteration context window (unused for Recraft)

    Returns:
        Standardized response dict
    """
    try:
        url = "https://external.api.recraft.ai/v1/images/imageToImage"
        headers = {
            "Authorization": f"Bearer {model_config.get('api_key', '')}",
        }

        # Decode base64 if string, otherwise use bytes directly
        if isinstance(source_image, str):
            image_bytes = base64.b64decode(source_image)
        else:
            image_bytes = source_image

        # Build context prompt
        context_prompt = prompt
        if context:
            history = " | ".join([c['prompt'] for c in context[-2:]])
            context_prompt = f"Previous: {history}. Now: {prompt}"

        # Multipart form data
        files = {
            'image': ('image.png', image_bytes, 'image/png'),
        }
        data = {
            'prompt': context_prompt,
            'model': 'recraftv3',
            'response_format': 'url',
        }

        response = requests.post(url, headers=headers, files=files, data=data, timeout=60)
        response.raise_for_status()
        result = response.json()

        # Get image URL from response
        image_url = result.get('data', [{}])[0].get('url')
        if not image_url:
            raise ValueError("No image URL in Recraft response")

        # Download image
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()
        image_base64 = base64.b64encode(img_response.content).decode('utf-8')

        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config.get('id', 'recraftv3'),
            'provider': 'recraft'
        }

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config.get('id', 'recraft'),
            'provider': 'recraft'
        }


def iterate_gemini(model_config: Dict, source_image: bytes, prompt: str, context: list) -> Dict:
    """
    Iterate on an image using Gemini multi-turn conversation.

    Gemini natively supports sending images with prompts for refinement.

    Args:
        model_config: Model configuration with API key
        source_image: Base64-encoded source image
        prompt: Refinement instruction
        context: Rolling 3-iteration context window

    Returns:
        Standardized response dict
    """
    try:
        client = genai.Client(api_key=model_config.get('api_key', ''))

        # Decode base64 if string
        if isinstance(source_image, str):
            image_bytes = base64.b64decode(source_image)
        else:
            image_bytes = source_image

        # Build prompt with context history
        context_prompt = prompt
        if context:
            history = " | ".join([f"Previous: {ctx['prompt']}" for ctx in context[-2:]])
            context_prompt = f"{history}. Now: {prompt}"

        # Create content with image and context-enriched prompt
        content_parts = [
            types.Part.from_bytes(data=image_bytes, mime_type='image/png'),
            types.Part.from_text(f"Edit this image: {context_prompt}")
        ]

        response = client.models.generate_content(
            model=model_config.get('id', 'gemini-2.0-flash-exp'),
            contents=content_parts,
            config=types.GenerateContentConfig(
                response_modalities=['Image']
            )
        )

        # Extract image from response
        if not response.candidates or len(response.candidates) == 0:
            raise ValueError("Gemini returned empty candidates array")

        image_data = None
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'inline_data') and part.inline_data:
                image_data = part.inline_data.data
                break

        if not image_data:
            raise ValueError("No image data found in Gemini response")

        image_base64 = base64.b64encode(image_data).decode('utf-8')

        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config.get('id', 'gemini-2.0-flash-exp'),
            'provider': 'google_gemini'
        }

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config.get('id', 'gemini'),
            'provider': 'google_gemini'
        }


def iterate_openai(model_config: Dict, source_image: bytes, prompt: str, context: list) -> Dict:
    """
    Iterate on an image using OpenAI images.edit endpoint.

    gpt-image-1 supports editing images with prompts.

    Args:
        model_config: Model configuration with API key
        source_image: Base64-encoded source image
        prompt: Refinement instruction
        context: Rolling 3-iteration context window (unused for OpenAI)

    Returns:
        Standardized response dict
    """
    try:
        client = OpenAI(api_key=model_config.get('api_key', ''), timeout=120.0)

        # Decode base64 if string
        if isinstance(source_image, str):
            image_bytes = base64.b64decode(source_image)
        else:
            image_bytes = source_image

        # Build context prompt
        context_prompt = prompt
        if context:
            history = " | ".join([c['prompt'] for c in context[-2:]])
            context_prompt = f"Previous: {history}. Now: {prompt}"

        # Use images.edit endpoint
        response = client.images.edit(
            model=model_config.get('id', 'gpt-image-1'),
            image=image_bytes,
            prompt=context_prompt,
            size="1024x1024"
        )

        if not response.data or len(response.data) == 0:
            raise ValueError("OpenAI returned empty data array")

        # gpt-image-1 returns base64
        if hasattr(response.data[0], 'b64_json') and response.data[0].b64_json:
            image_base64 = response.data[0].b64_json
        else:
            # Fall back to URL if present
            image_url = response.data[0].url
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()
            image_base64 = base64.b64encode(img_response.content).decode('utf-8')

        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config.get('id', 'gpt-image-1'),
            'provider': 'openai'
        }

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config.get('id', 'openai'),
            'provider': 'openai'
        }


def get_iterate_handler(provider: str) -> Callable:
    """
    Get the appropriate iteration handler for a provider.

    Args:
        provider: Provider identifier

    Returns:
        Iteration handler function
    """
    handlers = {
        'bfl': iterate_flux,
        'recraft': iterate_recraft,
        'google_gemini': iterate_gemini,
        'openai': iterate_openai,
    }

    handler = handlers.get(provider)
    if not handler:
        raise ValueError(f"No iteration handler for provider: {provider}")

    return handler


# ============================================================================
# OUTPAINTING HANDLERS
# ============================================================================

def outpaint_flux(model_config: Dict, source_image: bytes, preset: str, prompt: str) -> Dict:
    """
    Expand an image using FLUX Fill with edge mask.

    Args:
        model_config: Model configuration with API key
        source_image: Base64-encoded source image
        preset: Aspect preset ('16:9', '9:16', '1:1', '4:3', 'expand_all')
        prompt: Description for expanded regions

    Returns:
        Standardized response dict
    """
    try:
        from utils.outpaint import (
            calculate_expansion, pad_image_with_transparency,
            create_expansion_mask, get_image_dimensions
        )

        # Decode source image
        if isinstance(source_image, str):
            image_bytes = base64.b64decode(source_image)
        else:
            image_bytes = source_image

        # Get dimensions and calculate expansion
        width, height = get_image_dimensions(image_bytes)
        expansion = calculate_expansion(width, height, preset)

        # If no expansion needed, return original
        if expansion['left'] == 0 and expansion['right'] == 0 and \
           expansion['top'] == 0 and expansion['bottom'] == 0:
            return {
                'status': 'success',
                'image': source_image if isinstance(source_image, str) else base64.b64encode(source_image).decode('utf-8'),
                'model': model_config.get('id', 'flux-pro-1.1'),
                'provider': 'bfl'
            }

        # Create padded image and mask
        padded_image = pad_image_with_transparency(image_bytes, expansion)
        mask = create_expansion_mask(width, height, expansion, mask_format='base64')
        padded_base64 = base64.b64encode(padded_image).decode('utf-8')

        # BFL Fill endpoint
        url = "https://api.bfl.ai/v1/flux-pro-1.1-fill"
        headers = {
            "x-key": model_config.get('api_key', ''),
            "Content-Type": "application/json"
        }

        payload = {
            "image": padded_base64,
            "mask": mask,
            "prompt": f"Expand the image: {prompt}",
            "width": expansion['new_width'],
            "height": expansion['new_height']
        }

        # Start job
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        job_data = response.json()
        job_id = job_data.get('id')

        if not job_id:
            raise ValueError("No job ID returned from BFL Fill API")

        # Poll for result
        result_url = f"https://api.bfl.ai/v1/get_result?id={job_id}"
        for attempt in range(40):
            time.sleep(3)
            result_response = requests.get(result_url, headers=headers, timeout=10)
            result_response.raise_for_status()
            result_data = result_response.json()

            if result_data.get('status') == 'Ready':
                image_url = result_data['result']['sample']
                img_response = requests.get(image_url, timeout=30)
                img_response.raise_for_status()
                image_base64 = base64.b64encode(img_response.content).decode('utf-8')

                return {
                    'status': 'success',
                    'image': image_base64,
                    'model': model_config.get('id', 'flux-pro-1.1'),
                    'provider': 'bfl'
                }

            elif result_data.get('status') == 'Error':
                raise ValueError(f"BFL outpaint job failed: {result_data.get('error', 'Unknown')}")

        raise TimeoutError("BFL outpaint job timeout after 120 seconds")

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config.get('id', 'flux'),
            'provider': 'bfl'
        }


def outpaint_recraft(model_config: Dict, source_image: bytes, preset: str, prompt: str) -> Dict:
    """
    Expand an image using Recraft outpaint endpoint.

    Args:
        model_config: Model configuration with API key
        source_image: Base64-encoded source image
        preset: Aspect preset
        prompt: Description for expanded regions

    Returns:
        Standardized response dict
    """
    try:
        from utils.outpaint import calculate_expansion, get_image_dimensions

        # Decode source image
        if isinstance(source_image, str):
            image_bytes = base64.b64decode(source_image)
        else:
            image_bytes = source_image

        # Get dimensions and calculate expansion
        width, height = get_image_dimensions(image_bytes)
        expansion = calculate_expansion(width, height, preset)

        # Recraft outpaint endpoint
        url = "https://external.api.recraft.ai/v1/images/outpaint"
        headers = {
            "Authorization": f"Bearer {model_config.get('api_key', '')}",
        }

        # Calculate direction parameters for Recraft
        files = {
            'image': ('image.png', image_bytes, 'image/png'),
        }
        data = {
            'prompt': prompt,
            'model': 'recraftv3',
            'left': expansion['left'],
            'right': expansion['right'],
            'top': expansion['top'],
            'bottom': expansion['bottom'],
            'response_format': 'url',
        }

        response = requests.post(url, headers=headers, files=files, data=data, timeout=60)
        response.raise_for_status()
        result = response.json()

        # Get image URL from response
        image_url = result.get('data', [{}])[0].get('url')
        if not image_url:
            raise ValueError("No image URL in Recraft outpaint response")

        # Download image
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()
        image_base64 = base64.b64encode(img_response.content).decode('utf-8')

        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config.get('id', 'recraftv3'),
            'provider': 'recraft'
        }

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config.get('id', 'recraft'),
            'provider': 'recraft'
        }


def outpaint_gemini(model_config: Dict, source_image: bytes, preset: str, prompt: str) -> Dict:
    """
    Expand an image using Gemini prompt-based outpainting.

    Gemini doesn't have native outpainting, so we use prompt engineering.

    Args:
        model_config: Model configuration with API key
        source_image: Base64-encoded source image
        preset: Aspect preset
        prompt: Description for expanded regions

    Returns:
        Standardized response dict
    """
    try:
        from utils.outpaint import get_direction_description

        # Decode source image
        if isinstance(source_image, str):
            image_bytes = base64.b64decode(source_image)
        else:
            image_bytes = source_image

        direction = get_direction_description(preset)
        full_prompt = f"Extend this image {direction}. Fill the extended areas with: {prompt}"

        client = genai.Client(api_key=model_config.get('api_key', ''))

        content_parts = [
            types.Part.from_bytes(data=image_bytes, mime_type='image/png'),
            types.Part.from_text(full_prompt)
        ]

        response = client.models.generate_content(
            model=model_config.get('id', 'gemini-2.0-flash-exp'),
            contents=content_parts,
            config=types.GenerateContentConfig(
                response_modalities=['Image']
            )
        )

        if not response.candidates or len(response.candidates) == 0:
            raise ValueError("Gemini returned empty candidates array")

        image_data = None
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'inline_data') and part.inline_data:
                image_data = part.inline_data.data
                break

        if not image_data:
            raise ValueError("No image data found in Gemini outpaint response")

        image_base64 = base64.b64encode(image_data).decode('utf-8')

        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config.get('id', 'gemini-2.0-flash-exp'),
            'provider': 'google_gemini'
        }

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config.get('id', 'gemini'),
            'provider': 'google_gemini'
        }


def outpaint_openai(model_config: Dict, source_image: bytes, preset: str, prompt: str) -> Dict:
    """
    Expand an image using OpenAI images.edit with padded canvas.

    Args:
        model_config: Model configuration with API key
        source_image: Base64-encoded source image
        preset: Aspect preset
        prompt: Description for expanded regions

    Returns:
        Standardized response dict
    """
    try:
        from utils.outpaint import (
            calculate_expansion, pad_image_with_transparency,
            get_image_dimensions, get_openai_compatible_size
        )

        # Decode source image
        if isinstance(source_image, str):
            image_bytes = base64.b64decode(source_image)
        else:
            image_bytes = source_image

        # Get dimensions and calculate expansion
        width, height = get_image_dimensions(image_bytes)
        expansion = calculate_expansion(width, height, preset)

        # Create padded image with transparency
        padded_image = pad_image_with_transparency(image_bytes, expansion)

        client = OpenAI(api_key=model_config.get('api_key', ''), timeout=120.0)

        # Calculate appropriate size based on target aspect ratio
        target_size = get_openai_compatible_size(
            expansion['new_width'], expansion['new_height']
        )

        # Use images.edit with padded image
        # OpenAI will fill transparent areas
        response = client.images.edit(
            model=model_config.get('id', 'gpt-image-1'),
            image=padded_image,
            prompt=f"Expand the scene. Fill the transparent areas with: {prompt}",
            size=target_size
        )

        if not response.data or len(response.data) == 0:
            raise ValueError("OpenAI returned empty data array")

        if hasattr(response.data[0], 'b64_json') and response.data[0].b64_json:
            image_base64 = response.data[0].b64_json
        else:
            image_url = response.data[0].url
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()
            image_base64 = base64.b64encode(img_response.content).decode('utf-8')

        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config.get('id', 'gpt-image-1'),
            'provider': 'openai'
        }

    except Exception as e:
        return {
            'status': 'error',
            'error': sanitize_error_message(e),
            'model': model_config.get('id', 'openai'),
            'provider': 'openai'
        }


def get_outpaint_handler(provider: str) -> Callable:
    """
    Get the appropriate outpainting handler for a provider.

    Args:
        provider: Provider identifier

    Returns:
        Outpainting handler function
    """
    handlers = {
        'bfl': outpaint_flux,
        'recraft': outpaint_recraft,
        'google_gemini': outpaint_gemini,
        'openai': outpaint_openai,
    }

    handler = handlers.get(provider)
    if not handler:
        raise ValueError(f"No outpaint handler for provider: {provider}")

    return handler
