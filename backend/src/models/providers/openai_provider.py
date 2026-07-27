"""
OpenAI provider handlers.

Per ADR-5: ``handle_openai`` targets DALL-E 3 (``dall-e-3``) for generation,
while ``iterate_openai`` and ``outpaint_openai`` always use ``gpt-image-1``
because DALL-E 3 does not support ``images.edit``.
"""

from __future__ import annotations

import base64
from typing import Any

import requests

from config import api_client_timeout
from utils.clients import get_openai_client as _get_openai_client
from utils.clients import openai_call_timeout

from ._common import (
    GenerationParams,
    HandlerResult,
    ModelConfig,
    _build_context_prompt,
    _decode_source_image,
    _download_image_as_base64,
    _error_result,
    _success_result,
)

# Per ADR-5: gpt-image-1 supports images.edit; DALL-E 3 does not.
_EDIT_MODEL = "gpt-image-1"


def _call_timeout(model_config: ModelConfig) -> int:
    """Per-call timeout derived from the budget that binds this request.

    ``model_config["timeout"]`` is set on the refinement path only, where the
    chain is answered inside the HTTP request and has the gateway ceiling
    above it. /generate has no such key and keeps ``api_client_timeout``:
    after the async move it runs in a worker with 900s available.

    The SDK call and the image download are sequential, so they share the
    budget rather than each getting all of it -- see ``openai_call_timeout``.
    """
    return openai_call_timeout(model_config.get("timeout", api_client_timeout))


def handle_openai(
    model_config: ModelConfig, prompt: str, _params: GenerationParams
) -> HandlerResult:
    """Generate an image with DALL-E 3 (URL response, downloaded to base64)."""
    try:
        model_id = model_config["id"]
        timeout = _call_timeout(model_config)
        client = _get_openai_client(model_config.get("api_key", ""), timeout=timeout)

        response = client.images.generate(
            model=model_id, prompt=prompt, size="1024x1024", quality="standard", n=1
        )

        if not response.data or len(response.data) == 0:
            raise ValueError("OpenAI returned empty data array")

        image_url = response.data[0].url
        img_response = requests.get(image_url, timeout=timeout)
        img_response.raise_for_status()
        image_base64 = base64.b64encode(img_response.content).decode("utf-8")

        return _success_result(image_base64, model_config, "openai")

    except requests.Timeout:
        return _error_result(
            f"Image download timeout after {_call_timeout(model_config)} seconds",
            model_config,
            "openai",
        )

    except requests.ConnectionError as e:
        return _error_result(
            f"Image download connection failed: {e}",
            model_config,
            "openai",
        )

    except requests.HTTPError as e:
        return _error_result(
            f"Image download HTTP error: {e.response.status_code if e.response else 'unknown'}",
            model_config,
            "openai",
        )

    except Exception as e:
        return _error_result(e, model_config, "openai")


def iterate_openai(
    model_config: ModelConfig,
    source_image: str | bytes,
    prompt: str,
    context: list[dict[str, Any]],
) -> HandlerResult:
    """Iterate using OpenAI ``images.edit``.

    Always uses ``gpt-image-1`` regardless of ``model_config["id"]`` because
    DALL-E 3 does not support the edit endpoint (ADR-5).
    """
    try:
        timeout = _call_timeout(model_config)
        client = _get_openai_client(model_config.get("api_key", ""), timeout=timeout)
        image_bytes = _decode_source_image(source_image)
        context_prompt = _build_context_prompt(prompt, context)

        response = client.images.edit(
            model=_EDIT_MODEL,
            image=image_bytes,
            prompt=context_prompt,
            size="1024x1024",
        )

        if not response.data or len(response.data) == 0:
            raise ValueError("OpenAI returned empty data array")

        if hasattr(response.data[0], "b64_json") and response.data[0].b64_json:
            image_base64 = response.data[0].b64_json
        else:
            image_base64 = _download_image_as_base64(response.data[0].url, timeout=timeout)

        return _success_result(image_base64, model_config, "openai")

    except Exception as e:
        return _error_result(e, model_config, "openai")


def outpaint_openai(
    model_config: ModelConfig,
    source_image: str | bytes,
    preset: str,
    prompt: str,
) -> HandlerResult:
    """Outpaint using OpenAI ``images.edit`` with a padded canvas.

    Always uses ``gpt-image-1`` regardless of ``model_config["id"]`` (ADR-5).
    """
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

        timeout = _call_timeout(model_config)
        client = _get_openai_client(model_config.get("api_key", ""), timeout=timeout)
        target_size = get_openai_compatible_size(expansion["new_width"], expansion["new_height"])

        response = client.images.edit(
            model=_EDIT_MODEL,
            image=padded_image,
            prompt=f"Expand the scene. Fill the transparent areas with: {prompt}",
            size=target_size,
        )

        if not response.data or len(response.data) == 0:
            raise ValueError("OpenAI returned empty data array")

        if hasattr(response.data[0], "b64_json") and response.data[0].b64_json:
            image_base64 = response.data[0].b64_json
        else:
            image_base64 = _download_image_as_base64(response.data[0].url, timeout=timeout)

        return _success_result(image_base64, model_config, "openai")

    except Exception as e:
        return _error_result(e, model_config, "openai")
