"""
Per-provider handler modules.

Re-exports get_handler, get_iterate_handler, get_outpaint_handler, and
sanitize_error_message so the rest of the application can import from
``models.providers`` regardless of which provider files exist.
"""

from __future__ import annotations

from ._common import (
    HandlerError,
    HandlerFunc,
    HandlerResult,
    HandlerSuccess,
    IterateHandlerFunc,
    OutpaintHandlerFunc,
    sanitize_error_message,
)
from .firefly import handle_firefly, iterate_firefly, outpaint_firefly
from .gemini import handle_google_gemini, iterate_gemini, outpaint_gemini
from .nova import handle_nova, iterate_nova, outpaint_nova
from .openai_provider import handle_openai, iterate_openai, outpaint_openai

_GENERATE_HANDLERS: dict[str, HandlerFunc] = {
    "google_gemini": handle_google_gemini,
    "bedrock_nova": handle_nova,
    "openai": handle_openai,
    "adobe_firefly": handle_firefly,
}

_ITERATE_HANDLERS: dict[str, IterateHandlerFunc] = {
    "google_gemini": iterate_gemini,
    "bedrock_nova": iterate_nova,
    "openai": iterate_openai,
    "adobe_firefly": iterate_firefly,
}

_OUTPAINT_HANDLERS: dict[str, OutpaintHandlerFunc] = {
    "google_gemini": outpaint_gemini,
    "bedrock_nova": outpaint_nova,
    "openai": outpaint_openai,
    "adobe_firefly": outpaint_firefly,
}


def get_handler(provider: str) -> HandlerFunc:
    """Return generation handler for a provider."""
    handler = _GENERATE_HANDLERS.get(provider)
    if not handler:
        raise ValueError(f"Unknown provider: {provider}")
    return handler


def get_iterate_handler(provider: str) -> IterateHandlerFunc:
    """Return iteration handler for a provider."""
    handler = _ITERATE_HANDLERS.get(provider)
    if not handler:
        raise ValueError(f"No iteration handler for provider: {provider}")
    return handler


def get_outpaint_handler(provider: str) -> OutpaintHandlerFunc:
    """Return outpainting handler for a provider."""
    handler = _OUTPAINT_HANDLERS.get(provider)
    if not handler:
        raise ValueError(f"No outpaint handler for provider: {provider}")
    return handler


__all__ = [
    "HandlerError",
    "HandlerFunc",
    "HandlerResult",
    "HandlerSuccess",
    "IterateHandlerFunc",
    "OutpaintHandlerFunc",
    "get_handler",
    "get_iterate_handler",
    "get_outpaint_handler",
    "sanitize_error_message",
]
