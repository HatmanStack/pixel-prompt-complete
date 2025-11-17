"""
Provider-specific handlers for AI image generation.

Each handler implements image generation for a specific AI provider,
returning a standardized response format.
"""

import base64
import json
import os
import requests
import tempfile
import time
from typing import Dict, Any, Callable
from openai import OpenAI
import boto3
from google import genai
from google.genai import types


def handle_openai(model_config: Dict, prompt: str, _params: Dict) -> Dict:
    """
    Handle image generation for OpenAI (DALL-E 3).

    Args:
        model_config: Model configuration dict with 'name' and 'key'
        prompt: Text prompt for image generation
        _params: Generation parameters (unused - DALL-E 3 has fixed settings)

    Returns:
        Standardized response dict with status and image data
    """
    try:
        print(f"Calling OpenAI DALL-E 3 with prompt: {prompt[:50]}...")

        # Initialize OpenAI client with timeout
        client = OpenAI(api_key=model_config['key'], timeout=120.0)

        # Call DALL-E 3 image generation
        response = client.images.generate(
            model="dall-e-3",
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
        print(f"Downloading image from {image_url[:50]}...")
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()

        # Convert to base64
        image_base64 = base64.b64encode(img_response.content).decode('utf-8')

        print(f"OpenAI image generated successfully ({len(image_base64)} bytes)")

        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config['name'],
            'provider': 'openai'
        }

    except requests.Timeout:
        error_msg = "Image download timeout after 30 seconds"
        print(f"Error in handle_openai: {error_msg}")
        return {
            'status': 'error',
            'error': error_msg,
            'model': model_config['name'],
            'provider': 'openai'
        }

    except Exception as e:
        print(f"Error in handle_openai: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'model': model_config['name'],
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
        print(f"Calling Google Gemini 2.0 with prompt: {prompt[:50]}...")

        # Create Gemini client
        client = genai.Client(api_key=model_config['key'])

        # Generate image with multimodal model
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp-image-generation',
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

        print(f"Gemini image generated successfully ({len(image_base64)} bytes)")

        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config['name'],
            'provider': 'google_gemini'
        }

    except Exception as e:
        print(f"Error in handle_google_gemini: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'model': model_config['name'],
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
        print(f"Calling Google Imagen 3.0 with prompt: {prompt[:50]}...")

        # Create Imagen client
        client = genai.Client(api_key=model_config['key'])

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

        print(f"Imagen image generated successfully ({len(image_base64)} bytes)")

        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config['name'],
            'provider': 'google_imagen'
        }

    except Exception as e:
        print(f"Error in handle_google_imagen: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'model': model_config['name'],
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
        print(f"Calling AWS Bedrock Nova Canvas with prompt: {prompt[:50]}...")

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
            modelId='amazon.nova-canvas-v1:0',
            body=json.dumps(request_body)
        )

        # Parse response
        response_body = json.loads(response['body'].read())

        # Validate response structure
        if 'images' not in response_body or len(response_body['images']) == 0:
            raise ValueError("Bedrock Nova returned empty images array")

        # Extract base64 image from response
        image_base64 = response_body['images'][0]

        print(f"Bedrock Nova image generated successfully ({len(image_base64)} bytes)")

        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config['name'],
            'provider': 'bedrock_nova'
        }

    except Exception as e:
        print(f"Error in handle_bedrock_nova: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'model': model_config['name'],
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
        print(f"Calling AWS Bedrock SD 3.5 Large with prompt: {prompt[:50]}...")

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
            modelId='stability.sd3-5-large-v1:0',
            body=json.dumps(request_body)
        )

        # Parse response
        response_body = json.loads(response['body'].read())

        # Validate response structure
        if 'images' not in response_body or len(response_body['images']) == 0:
            raise ValueError("Bedrock SD returned empty images array")

        # Extract base64 image from response
        image_base64 = response_body['images'][0]

        print(f"Bedrock SD image generated successfully ({len(image_base64)} bytes)")

        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config['name'],
            'provider': 'bedrock_sd'
        }

    except Exception as e:
        print(f"Error in handle_bedrock_sd: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'model': model_config['name'],
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
        print(f"Calling Stability AI SD3 with prompt: {prompt[:50]}...")

        # Stability AI API endpoint
        url = "https://api.stability.ai/v2beta/stable-image/generate/sd3"

        # Headers
        headers = {
            "authorization": f"Bearer {model_config['key']}",
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

        print(f"Stability AI image generated successfully ({len(image_base64)} bytes)")

        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config['name'],
            'provider': 'stability'
        }

    except requests.Timeout:
        error_msg = "Stability AI request timeout after 60 seconds"
        print(f"Error in handle_stability: {error_msg}")
        return {
            'status': 'error',
            'error': error_msg,
            'model': model_config['name'],
            'provider': 'stability'
        }

    except Exception as e:
        print(f"Error in handle_stability: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'model': model_config['name'],
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
        model_name_lower = model_config['name'].lower()

        # Determine endpoint based on model name
        if 'pro' in model_name_lower:
            endpoint = "flux-pro-1.1"
        else:
            endpoint = "flux-dev"

        print(f"Calling BFL {endpoint} with prompt: {prompt[:50]}...")

        # Start job
        start_url = f"https://api.bfl.ai/v1/{endpoint}"
        headers = {
            "x-key": model_config['key'],
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

        print(f"BFL job started: {job_id}, polling for result...")

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
            print(f"BFL job status: {status} (attempt {attempt}/{max_attempts})")

            if status == 'Ready':
                # Download image from result URL
                image_url = result_data['result']['sample']
                img_response = requests.get(image_url, timeout=30)
                img_response.raise_for_status()

                # Convert to base64
                image_base64 = base64.b64encode(img_response.content).decode('utf-8')

                print(f"BFL image generated successfully ({len(image_base64)} bytes)")

                return {
                    'status': 'success',
                    'image': image_base64,
                    'model': model_config['name'],
                    'provider': 'bfl'
                }

            elif status == 'Error':
                error_msg = result_data.get('error', 'Unknown error')
                raise ValueError(f"BFL job failed: {error_msg}")

        # Timeout
        raise TimeoutError(f"BFL job timeout after {max_attempts * 3} seconds")

    except Exception as e:
        print(f"Error in handle_bfl: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'model': model_config['name'],
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
        print(f"Calling Recraft v3 with prompt: {prompt[:50]}...")

        # Recraft uses OpenAI-compatible API with custom base URL
        client = OpenAI(
            api_key=model_config['key'],
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
        print(f"Downloading Recraft image from {image_url[:50]}...")
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()

        # Convert to base64
        image_base64 = base64.b64encode(img_response.content).decode('utf-8')

        print(f"Recraft image generated successfully ({len(image_base64)} bytes)")

        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config['name'],
            'provider': 'recraft'
        }

    except Exception as e:
        print(f"Error in handle_recraft: {str(e)}")
        return {
            'status': 'error',
            'error': str(e),
            'model': model_config['name'],
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
        print(f"Calling generic OpenAI-compatible handler for {model_config['name']}")
        print(f"Attempting with prompt: {prompt[:50]}...")

        # Try as OpenAI-compatible API
        # Use the model name as-is
        client_kwargs = {
            'api_key': model_config['key'],
            'timeout': 120.0
        }

        # Support custom base_url for OpenAI-compatible providers
        if 'base_url' in model_config:
            client_kwargs['base_url'] = model_config['base_url']

        client = OpenAI(**client_kwargs)

        response = client.images.generate(
            model=model_config['name'],
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

        print(f"Generic handler succeeded ({len(image_base64)} bytes)")

        return {
            'status': 'success',
            'image': image_base64,
            'model': model_config['name'],
            'provider': 'generic'
        }

    except Exception as e:
        error_msg = f"Generic handler failed (model may not be OpenAI-compatible): {str(e)}"
        print(f"Error in handle_generic: {error_msg}")
        return {
            'status': 'error',
            'error': error_msg,
            'model': model_config['name'],
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
        print(f"No specific handler for provider '{provider}', using generic handler")

    return handler
