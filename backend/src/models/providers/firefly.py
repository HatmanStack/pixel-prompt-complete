"""
Adobe Firefly provider handlers.

OAuth2 access tokens are cached at module level with a 50-minute TTL
(Adobe IMS tokens are valid for 24 hours). The cache lives within a
single Lambda container and resets on cold start.
"""

from __future__ import annotations

import threading
import time as _time
from typing import Any

import requests

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

_TOKEN_URL = "https://ims-na1.adobelogin.com/ims/token/v3"
_GENERATE_URL = "https://firefly-api.adobe.io/v3/images/generate"
_EXPAND_URL = "https://firefly-api.adobe.io/v3/images/expand"
_STORAGE_URL = "https://firefly-api.adobe.io/v2/storage/image"
_TOKEN_TIMEOUT = 10
_API_TIMEOUT = 60

# Module-level token cache (lives within a single Lambda container).
# Assumes one set of Firefly credentials per container (single config).
_token_lock = threading.Lock()
_cached_token: str | None = None
_cached_token_expiry: float = 0.0
_TOKEN_TTL = 50 * 60  # 50 minutes (Adobe tokens last 24h, refresh well before expiry)


def _get_firefly_access_token(client_id: str, client_secret: str) -> str:
    """Fetch an OAuth2 access token from Adobe IMS."""
    if not client_id or not client_secret:
        raise ValueError("Firefly client_id and client_secret are required")

    response = requests.post(
        _TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "openid,AdobeID,firefly_api",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=_TOKEN_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise ValueError("Adobe IMS returned no access_token")
    return token


def _get_or_refresh_token(client_id: str, client_secret: str) -> str:
    """Return a cached access token, refreshing if expired or missing."""
    global _cached_token, _cached_token_expiry
    with _token_lock:
        now = _time.monotonic()
        if _cached_token and now < _cached_token_expiry:
            return _cached_token
        token = _get_firefly_access_token(client_id, client_secret)
        _cached_token = token
        _cached_token_expiry = now + _TOKEN_TTL
        return token


def _firefly_headers(token: str, client_id: str, json_body: bool = True) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-key": client_id,
    }
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def _upload_source_image(image_bytes: bytes, token: str, client_id: str) -> str:
    """Upload an image to Firefly storage and return the upload ID."""
    response = requests.post(
        _STORAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "x-api-key": client_id,
            "Content-Type": "image/png",
        },
        data=image_bytes,
        timeout=_API_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    upload_id = (payload.get("images") or [{}])[0].get("id") or payload.get("id")
    if not upload_id:
        raise ValueError("Firefly storage upload returned no id")
    return upload_id


def _extract_firefly_image_url(payload: dict[str, Any]) -> str:
    outputs = payload.get("outputs") or []
    if not outputs:
        raise ValueError("Firefly returned empty outputs array")
    image = outputs[0].get("image") or {}
    url = image.get("url") or outputs[0].get("url")
    if not url:
        raise ValueError("Firefly response missing image URL")
    return url


def handle_firefly(
    model_config: ModelConfig, prompt: str, _params: GenerationParams
) -> HandlerResult:
    """Generate an image with Adobe Firefly Image5."""
    try:
        client_id = model_config.get("client_id", "")
        client_secret = model_config.get("client_secret", "")
        token = _get_or_refresh_token(client_id, client_secret)

        body = {
            "prompt": prompt,
            "n": 1,
            "size": {"width": 1024, "height": 1024},
            "contentClass": "photo",
        }
        response = requests.post(
            _GENERATE_URL,
            headers=_firefly_headers(token, client_id),
            json=body,
            timeout=_API_TIMEOUT,
        )
        response.raise_for_status()

        image_url = _extract_firefly_image_url(response.json())
        image_base64 = _download_image_as_base64(image_url)
        return _success_result(image_base64, model_config, "adobe_firefly")

    except Exception as e:
        return _error_result(e, model_config, "adobe_firefly")


def iterate_firefly(
    model_config: ModelConfig,
    source_image: str | bytes,
    prompt: str,
    context: list[dict[str, Any]],
) -> HandlerResult:
    """Iterate via Firefly structure reference (uploads source image first)."""
    try:
        client_id = model_config.get("client_id", "")
        client_secret = model_config.get("client_secret", "")
        token = _get_or_refresh_token(client_id, client_secret)

        image_bytes = _decode_source_image(source_image)
        upload_id = _upload_source_image(image_bytes, token, client_id)
        context_prompt = _build_context_prompt(prompt, context)

        body = {
            "prompt": context_prompt,
            "n": 1,
            "size": {"width": 1024, "height": 1024},
            "structure": {
                "imageReference": {"source": {"uploadId": upload_id}},
                "strength": 70,
            },
        }
        response = requests.post(
            _GENERATE_URL,
            headers=_firefly_headers(token, client_id),
            json=body,
            timeout=_API_TIMEOUT,
        )
        response.raise_for_status()

        image_url = _extract_firefly_image_url(response.json())
        image_base64 = _download_image_as_base64(image_url)
        return _success_result(image_base64, model_config, "adobe_firefly")

    except Exception as e:
        return _error_result(e, model_config, "adobe_firefly")


def outpaint_firefly(
    model_config: ModelConfig,
    source_image: str | bytes,
    preset: str,
    prompt: str,
) -> HandlerResult:
    """Outpaint via Firefly generative expand."""
    try:
        from utils.outpaint import calculate_expansion, get_image_dimensions

        client_id = model_config.get("client_id", "")
        client_secret = model_config.get("client_secret", "")
        token = _get_or_refresh_token(client_id, client_secret)

        image_bytes = _decode_source_image(source_image)
        width, height = get_image_dimensions(image_bytes)
        expansion = calculate_expansion(width, height, preset)
        upload_id = _upload_source_image(image_bytes, token, client_id)

        body = {
            "prompt": prompt,
            "n": 1,
            "size": {
                "width": expansion["new_width"],
                "height": expansion["new_height"],
            },
            "image": {"source": {"uploadId": upload_id}},
        }
        response = requests.post(
            _EXPAND_URL,
            headers=_firefly_headers(token, client_id),
            json=body,
            timeout=_API_TIMEOUT,
        )
        response.raise_for_status()

        image_url = _extract_firefly_image_url(response.json())
        image_base64 = _download_image_as_base64(image_url)
        return _success_result(image_base64, model_config, "adobe_firefly")

    except Exception as e:
        return _error_result(e, model_config, "adobe_firefly")
