"""
Shared helpers and types for provider handler modules.

Each provider module imports from this file. Uses modern Python 3.13
type syntax (str | bytes, dict, list) instead of legacy typing imports.
"""

from __future__ import annotations

import base64
import re
from typing import Any, Callable, Literal, NotRequired, TypedDict

import requests

from config import image_download_timeout

# ----------------------------------------------------------------------------
# Typed return contracts
# ----------------------------------------------------------------------------


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
ModelConfig = dict[str, Any]
GenerationParams = dict[str, Any]
HandlerFunc = Callable[[ModelConfig, str, GenerationParams], HandlerResult]
IterateHandlerFunc = Callable[[ModelConfig, bytes | str, str, list[dict[str, Any]]], HandlerResult]
OutpaintHandlerFunc = Callable[[ModelConfig, bytes | str, str, str], HandlerResult]


# ----------------------------------------------------------------------------
# Source image / context helpers
# ----------------------------------------------------------------------------


def _decode_source_image(source_image: str | bytes) -> bytes:
    """Common base64 decode logic used by all iterate/outpaint handlers."""
    if isinstance(source_image, str):
        return base64.b64decode(source_image)
    return source_image


def _build_context_prompt(prompt: str, context: list[dict[str, Any]], max_history: int = 3) -> str:
    """Build context-enriched prompt from iteration history."""
    if not context:
        return prompt
    history = " | ".join([c["prompt"] for c in context[-max_history:]])
    return f"Previous: {history}. Now: {prompt}"


def _ensure_base64(source_image: str | bytes) -> str:
    """Ensure image is base64-encoded string."""
    if isinstance(source_image, str):
        return source_image
    return base64.b64encode(source_image).decode("utf-8")


def _extract_gemini_image(response: Any) -> str:
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


# ----------------------------------------------------------------------------
# Error sanitization
# ----------------------------------------------------------------------------


def sanitize_error_message(error: Exception | str) -> str:
    """
    Sanitize error messages to remove sensitive information like API keys.
    """
    error_str = str(error)

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
    # Generic long alphanumeric strings that look like keys
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
