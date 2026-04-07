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
import re
from typing import Any, Callable, Dict, List, Literal, NotRequired, TypedDict, Union

import requests
from google.genai import types

from config import (
    api_client_timeout,
    image_download_timeout,
)
from utils.clients import get_genai_client as _get_genai_client
from utils.clients import get_openai_client as _get_openai_client


# Common handler helpers
def _decode_source_image(source_image: Union[str, bytes]) -> bytes:
    """Common base64 decode logic used by all iterate/outpaint handlers."""
    if isinstance(source_image, str):
        return base64.b64decode(source_image)
    return source_image


def _build_context_prompt(prompt: str, context: List[Dict[str, Any]], max_history: int = 3) -> str:
    """Build context-enriched prompt from iteration history."""
    if not context:
        return prompt
    history = " | ".join([c["prompt"] for c in context[-max_history:]])
    return f"Previous: {history}. Now: {prompt}"


def _ensure_base64(source_image: Union[str, bytes]) -> str:
    """Ensure image is base64-encoded string."""
    if isinstance(source_image, str):
        return source_image
    return base64.b64encode(source_image).decode("utf-8")


def _extract_gemini_image(response) -> str:
    """Extract image data from Gemini response and return as base64."""
    if not response.candidates or len(response.candidates) == 0:
        raise ValueError("Gemini returned empty candidates array")

    for part in response.candidates[0].content.parts:
        if hasattr(part, "inline_data") and part.inline_data:
            return base64.b64encode(part.inline_data.data).decode("utf-8")

    raise ValueError("No image data found in Gemini response")


def _download_image_as_base64(url: str, timeout: int = image_download_timeout) -> str:
    """Download image from URL and return as base64."""
    img_response = requests.get(url, timeout=timeout)
    img_response.raise_for_status()
    return base64.b64encode(img_response.content).decode("utf-8")


# Typed return dicts for handler functions
class HandlerSuccess(TypedDict):
    status: Literal["success"]
    image: str
    model: NotRequired[str]
    provider: NotRequired[str]


class HandlerError(TypedDict):
    status: Literal["error"]
    error: str
    model: NotRequired[str]
    provider: NotRequired[str]


HandlerResult = HandlerSuccess | HandlerError

# Type aliases for handler contracts
ModelConfig = Dict[str, Any]
GenerationParams = Dict[str, Any]
HandlerFunc = Callable[[ModelConfig, str, GenerationParams], HandlerResult]
IterateHandlerFunc = Callable[[ModelConfig, bytes, str, List[Dict[str, Any]]], HandlerResult]
OutpaintHandlerFunc = Callable[[ModelConfig, bytes, str, str], HandlerResult]


def sanitize_error_message(error: Union[Exception, str]) -> str:
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
    error_str = re.sub(r"Bearer\s+[A-Za-z0-9\-_\.]+", "Bearer [REDACTED]", error_str)
    # API keys in various formats
    error_str = re.sub(
        r'(api[_-]?key|apikey|key|token|secret|password|authorization)["\']?\s*[:=]\s*["\']?[A-Za-z0-9\-_\.]+["\']?',
        r"\1=[REDACTED]",
        error_str,
        flags=re.IGNORECASE,
    )
    # sk- prefixed keys (OpenAI style)
    error_str = re.sub(r"sk-[A-Za-z0-9\-_]{20,}", "[REDACTED_KEY]", error_str)
    # Generic long alphanumeric strings that look like keys (32+ chars, mixed-case + digits)
    # Requires uppercase, lowercase, AND digits to avoid redacting session IDs / UUIDs
    error_str = re.sub(
        r"(?=[A-Za-z0-9]{32,})(?=.*[A-Z])(?=.*[a-z])(?=.*\d)[A-Za-z0-9]{32,}",
        "[REDACTED]",
        error_str,
    )

    return error_str


def _success_result(image: str, model_config: ModelConfig, provider: str) -> HandlerResult:
    """Build standardized success response."""
    return {
        "status": "success",
        "image": image,
        "model": model_config.get("id", ""),
        "provider": provider,
    }


def _error_result(
    error: Exception | str, model_config: ModelConfig, provider: str
) -> HandlerResult:
    """Build standardized error response."""
    msg = sanitize_error_message(error) if isinstance(error, Exception) else error
    return {
        "status": "error",
        "error": msg,
        "model": model_config.get("id", ""),
        "provider": provider,
    }


def handle_openai(
    model_config: ModelConfig, prompt: str, _params: GenerationParams
) -> HandlerResult:
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

        client = _get_openai_client(model_config.get("api_key", ""))

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
                model=model_id, prompt=prompt, size="1024x1024", quality="standard", n=1
            )

            # Validate response structure
            if not response.data or len(response.data) == 0:
                raise ValueError("OpenAI returned empty data array")

            # Extract image URL from response
            image_url = response.data[0].url

            # Download image
            img_response = requests.get(image_url, timeout=image_download_timeout)
            img_response.raise_for_status()

            # Convert to base64
            image_base64 = base64.b64encode(img_response.content).decode("utf-8")

        return _success_result(image_base64, model_config, "openai")

    except requests.Timeout:
        return _error_result(
            f"Image download timeout after {image_download_timeout} seconds", model_config, "openai"
        )

    except Exception as e:
        return _error_result(e, model_config, "openai")


def handle_google_gemini(
    model_config: ModelConfig, prompt: str, _params: GenerationParams
) -> HandlerResult:
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
        client = _get_genai_client(model_config.get("api_key", ""))

        response = client.models.generate_content(
            model=model_config["id"],
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["Text", "Image"]),
        )

        image_base64 = _extract_gemini_image(response)

        return _success_result(image_base64, model_config, "google_gemini")

    except Exception as e:
        return _error_result(e, model_config, "google_gemini")


def get_handler(provider: str) -> HandlerFunc:
    """
    Get the appropriate handler function for a provider.

    Args:
        provider: Provider identifier (e.g., 'openai', 'google_gemini', 'bfl', 'recraft')

    Returns:
        Handler function for the provider

    Raises:
        ValueError: If provider is not recognized
    """
    handlers = {
        "openai": handle_openai,
        "google_gemini": handle_google_gemini,
    }

    handler = handlers.get(provider)
    if not handler:
        raise ValueError(f"Unknown provider: {provider}")

    return handler


# ============================================================================
# ITERATION HANDLERS
# ============================================================================


def iterate_gemini(
    model_config: ModelConfig,
    source_image: Union[str, bytes],
    prompt: str,
    context: List[Dict[str, Any]],
) -> HandlerResult:
    """Iterate on an image using Gemini multi-turn conversation."""
    try:
        client = _get_genai_client(model_config.get("api_key", ""))
        image_bytes = _decode_source_image(source_image)
        context_prompt = _build_context_prompt(prompt, context)

        content_parts = [
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            types.Part.from_text(f"Edit this image: {context_prompt}"),
        ]

        response = client.models.generate_content(
            model=model_config.get("id", "gemini-2.5-flash-image"),
            contents=content_parts,
            config=types.GenerateContentConfig(response_modalities=["Image"]),
        )

        image_base64 = _extract_gemini_image(response)

        return _success_result(image_base64, model_config, "google_gemini")

    except Exception as e:
        return _error_result(e, model_config, "google_gemini")


def iterate_openai(
    model_config: ModelConfig,
    source_image: Union[str, bytes],
    prompt: str,
    context: List[Dict[str, Any]],
) -> HandlerResult:
    """Iterate on an image using OpenAI images.edit endpoint."""
    try:
        client = _get_openai_client(model_config.get("api_key", ""), timeout=api_client_timeout)
        image_bytes = _decode_source_image(source_image)
        context_prompt = _build_context_prompt(prompt, context)

        response = client.images.edit(
            model=model_config.get("id", "gpt-image-1"),
            image=image_bytes,
            prompt=context_prompt,
            size="1024x1024",
        )

        if not response.data or len(response.data) == 0:
            raise ValueError("OpenAI returned empty data array")

        if hasattr(response.data[0], "b64_json") and response.data[0].b64_json:
            image_base64 = response.data[0].b64_json
        else:
            image_base64 = _download_image_as_base64(response.data[0].url)

        return _success_result(image_base64, model_config, "openai")

    except Exception as e:
        return _error_result(e, model_config, "openai")


def get_iterate_handler(provider: str) -> IterateHandlerFunc:
    """
    Get the appropriate iteration handler for a provider.

    Args:
        provider: Provider identifier

    Returns:
        Iteration handler function
    """
    handlers = {
        "google_gemini": iterate_gemini,
        "openai": iterate_openai,
    }

    handler = handlers.get(provider)
    if not handler:
        raise ValueError(f"No iteration handler for provider: {provider}")

    return handler


# ============================================================================
# OUTPAINTING HANDLERS
# ============================================================================


def outpaint_gemini(
    model_config: ModelConfig, source_image: Union[str, bytes], preset: str, prompt: str
) -> HandlerResult:
    """Expand an image using Gemini prompt-based outpainting."""
    try:
        from utils.outpaint import get_direction_description

        image_bytes = _decode_source_image(source_image)
        direction = get_direction_description(preset)
        full_prompt = f"Extend this image {direction}. Fill the extended areas with: {prompt}"

        client = _get_genai_client(model_config.get("api_key", ""))

        content_parts = [
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            types.Part.from_text(full_prompt),
        ]

        response = client.models.generate_content(
            model=model_config.get("id", "gemini-2.5-flash-image"),
            contents=content_parts,
            config=types.GenerateContentConfig(response_modalities=["Image"]),
        )

        image_base64 = _extract_gemini_image(response)

        return _success_result(image_base64, model_config, "google_gemini")

    except Exception as e:
        return _error_result(e, model_config, "google_gemini")


def outpaint_openai(
    model_config: ModelConfig, source_image: Union[str, bytes], preset: str, prompt: str
) -> HandlerResult:
    """Expand an image using OpenAI images.edit with padded canvas."""
    try:
        from utils.outpaint import (
            calculate_expansion,
            get_image_dimensions,
            get_openai_compatible_size,
            pad_image_with_transparency,
        )

        image_bytes = _decode_source_image(source_image)
        width, height = get_image_dimensions(image_bytes)
        expansion = calculate_expansion(width, height, preset)
        padded_image = pad_image_with_transparency(image_bytes, expansion)

        client = _get_openai_client(model_config.get("api_key", ""), timeout=api_client_timeout)
        target_size = get_openai_compatible_size(expansion["new_width"], expansion["new_height"])

        response = client.images.edit(
            model=model_config.get("id", "gpt-image-1"),
            image=padded_image,
            prompt=f"Expand the scene. Fill the transparent areas with: {prompt}",
            size=target_size,
        )

        if not response.data or len(response.data) == 0:
            raise ValueError("OpenAI returned empty data array")

        if hasattr(response.data[0], "b64_json") and response.data[0].b64_json:
            image_base64 = response.data[0].b64_json
        else:
            image_base64 = _download_image_as_base64(response.data[0].url)

        return _success_result(image_base64, model_config, "openai")

    except Exception as e:
        return _error_result(e, model_config, "openai")


def get_outpaint_handler(provider: str) -> OutpaintHandlerFunc:
    """
    Get the appropriate outpainting handler for a provider.

    Args:
        provider: Provider identifier

    Returns:
        Outpainting handler function
    """
    handlers = {
        "google_gemini": outpaint_gemini,
        "openai": outpaint_openai,
    }

    handler = handlers.get(provider)
    if not handler:
        raise ValueError(f"No outpaint handler for provider: {provider}")

    return handler
