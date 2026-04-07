"""
Amazon Nova Canvas provider handlers (via AWS Bedrock).

Auth uses the Lambda execution role's ``bedrock:InvokeModel`` permission;
no API key is required.
"""

from __future__ import annotations

import json
from typing import Any

from utils.clients import get_bedrock_client

from ._common import (
    GenerationParams,
    HandlerResult,
    ModelConfig,
    _build_context_prompt,
    _decode_source_image,
    _ensure_base64,
    _error_result,
    _success_result,
)

_DEFAULT_WIDTH = 1024
_DEFAULT_HEIGHT = 1024


def _invoke_nova(model_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Invoke a Nova Canvas model and return the parsed response body."""
    client = get_bedrock_client()
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    return json.loads(response["body"].read().decode("utf-8"))


def _extract_nova_image(payload: dict[str, Any]) -> str:
    """Extract the first image from a Nova Canvas response payload."""
    images = payload.get("images") or []
    if not images:
        raise ValueError("Nova Canvas returned empty images array")
    return images[0]


def handle_nova(model_config: ModelConfig, prompt: str, _params: GenerationParams) -> HandlerResult:
    """Generate an image with Nova Canvas via Bedrock."""
    try:
        body = {
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {"text": prompt},
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "width": _DEFAULT_WIDTH,
                "height": _DEFAULT_HEIGHT,
                "cfgScale": 8.0,
            },
        }
        payload = _invoke_nova(model_config["id"], body)
        image_base64 = _extract_nova_image(payload)
        return _success_result(image_base64, model_config, "bedrock_nova")

    except Exception as e:
        return _error_result(e, model_config, "bedrock_nova")


def iterate_nova(
    model_config: ModelConfig,
    source_image: str | bytes,
    prompt: str,
    context: list[dict[str, Any]],
) -> HandlerResult:
    """Iterate using Nova Canvas IMAGE_VARIATION task type."""
    try:
        source_b64 = _ensure_base64(source_image)
        context_prompt = _build_context_prompt(prompt, context)

        body = {
            "taskType": "IMAGE_VARIATION",
            "imageVariationParams": {
                "text": context_prompt,
                "images": [source_b64],
                "similarityStrength": 0.7,
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "width": _DEFAULT_WIDTH,
                "height": _DEFAULT_HEIGHT,
            },
        }
        payload = _invoke_nova(model_config["id"], body)
        image_base64 = _extract_nova_image(payload)
        return _success_result(image_base64, model_config, "bedrock_nova")

    except Exception as e:
        return _error_result(e, model_config, "bedrock_nova")


def outpaint_nova(
    model_config: ModelConfig,
    source_image: str | bytes,
    preset: str,
    prompt: str,
) -> HandlerResult:
    """Expand an image using Nova Canvas OUTPAINTING task type."""
    try:
        from utils.outpaint import calculate_expansion, get_image_dimensions

        image_bytes = _decode_source_image(source_image)
        width, height = get_image_dimensions(image_bytes)
        expansion = calculate_expansion(width, height, preset)

        if (
            expansion["left"] == 0
            and expansion["right"] == 0
            and expansion["top"] == 0
            and expansion["bottom"] == 0
        ):
            return _success_result(_ensure_base64(source_image), model_config, "bedrock_nova")

        body = {
            "taskType": "OUTPAINTING",
            "outPaintingParams": {
                "text": prompt,
                "image": _ensure_base64(source_image),
                "outPaintingMode": "DEFAULT",
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "width": expansion["new_width"],
                "height": expansion["new_height"],
            },
        }
        payload = _invoke_nova(model_config["id"], body)
        image_base64 = _extract_nova_image(payload)
        return _success_result(image_base64, model_config, "bedrock_nova")

    except Exception as e:
        return _error_result(e, model_config, "bedrock_nova")
