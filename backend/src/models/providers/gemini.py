"""
Google Gemini provider handlers (Nano Banana 2 / gemini-3.1-flash-image-preview).

Implements all 3 handler types: generate, iterate, outpaint.
"""

from __future__ import annotations

from typing import Any

from google.genai import types

from config import api_client_timeout
from utils.clients import gemini_call_timeout
from utils.clients import get_genai_client as _get_genai_client

from ._common import (
    GenerationParams,
    HandlerResult,
    ModelConfig,
    _build_context_prompt,
    _decode_source_image,
    _error_result,
    _extract_gemini_image,
    _success_result,
)


def _call_timeout(model_config: ModelConfig) -> float:
    """Timeout derived from the budget that binds this request.

    ``model_config["timeout"]`` is set on the refinement path only, where the
    whole chain is answered inside the HTTP request and so has the gateway
    ceiling above it. /generate has no such key and keeps
    ``api_client_timeout``: after the async move it runs in a worker
    invocation with 900s available and no gateway in front of it.
    """
    return gemini_call_timeout(model_config.get("timeout", api_client_timeout))


def handle_google_gemini(
    model_config: ModelConfig, prompt: str, _params: GenerationParams
) -> HandlerResult:
    """Generate an image with Google Gemini."""
    try:
        client = _get_genai_client(
            model_config.get("api_key", ""), timeout=_call_timeout(model_config)
        )

        response = client.models.generate_content(
            model=model_config["id"],
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["Text", "Image"]),
        )

        image_base64 = _extract_gemini_image(response)
        return _success_result(image_base64, model_config, "google_gemini")

    except Exception as e:
        return _error_result(e, model_config, "google_gemini")


def iterate_gemini(
    model_config: ModelConfig,
    source_image: str | bytes,
    prompt: str,
    context: list[dict[str, Any]],
) -> HandlerResult:
    """Iterate on an image using Gemini multi-turn conversation."""
    try:
        client = _get_genai_client(
            model_config.get("api_key", ""), timeout=_call_timeout(model_config)
        )
        image_bytes = _decode_source_image(source_image)
        context_prompt = _build_context_prompt(prompt, context)

        content_parts = [
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            types.Part.from_text(f"Edit this image: {context_prompt}"),
        ]

        response = client.models.generate_content(
            model=model_config.get("id", "gemini-3.1-flash-image-preview"),
            contents=content_parts,
            config=types.GenerateContentConfig(response_modalities=["Image"]),
        )

        image_base64 = _extract_gemini_image(response)
        return _success_result(image_base64, model_config, "google_gemini")

    except Exception as e:
        return _error_result(e, model_config, "google_gemini")


def outpaint_gemini(
    model_config: ModelConfig,
    source_image: str | bytes,
    preset: str,
    prompt: str,
) -> HandlerResult:
    """Expand an image using Gemini prompt-based outpainting."""
    try:
        from utils.outpaint import get_direction_description

        image_bytes = _decode_source_image(source_image)
        direction = get_direction_description(preset)
        full_prompt = f"Extend this image {direction}. Fill the extended areas with: {prompt}"

        client = _get_genai_client(
            model_config.get("api_key", ""), timeout=_call_timeout(model_config)
        )

        content_parts = [
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            types.Part.from_text(full_prompt),
        ]

        response = client.models.generate_content(
            model=model_config.get("id", "gemini-3.1-flash-image-preview"),
            contents=content_parts,
            config=types.GenerateContentConfig(response_modalities=["Image"]),
        )

        image_base64 = _extract_gemini_image(response)
        return _success_result(image_base64, model_config, "google_gemini")

    except Exception as e:
        return _error_result(e, model_config, "google_gemini")
