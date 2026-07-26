"""
Cached SDK client factories for Lambda container reuse.

Provides singleton clients keyed by API key (and relevant kwargs)
so that repeated calls within the same Lambda invocation reuse
the same HTTP connection pool.
"""

from typing import Any, Dict

import boto3
from botocore.config import Config as BotoConfig
from google import genai
from openai import OpenAI

from config import api_client_timeout, aws_region

# Module-level client singletons for Lambda container reuse
_openai_clients: Dict[Any, OpenAI] = {}
_genai_clients: Dict[Any, genai.Client] = {}
_bedrock_clients: Dict[str, Any] = {}


def get_openai_client(api_key: str, **kwargs) -> OpenAI:
    """Get or create a cached OpenAI client keyed by api_key and relevant kwargs.

    Note: The cache key only includes ``base_url`` and ``timeout``.  If a new kwarg
    is added to callers that affects client behaviour, it **must** be added to the
    ``_CACHE_KEY_KWARGS`` set below to avoid returning a stale cached client.
    """
    _CACHE_KEY_KWARGS = ("base_url", "timeout")
    _CACHE_KEY_DEFAULTS = {"timeout": api_client_timeout}
    normalized = {k: kwargs.get(k, _CACHE_KEY_DEFAULTS.get(k)) for k in _CACHE_KEY_KWARGS}
    extra = tuple(sorted((k, v) for k, v in normalized.items() if v is not None))
    cache_key = (api_key or "__default__", extra)
    if cache_key not in _openai_clients:
        _openai_clients[cache_key] = OpenAI(
            api_key=api_key or None,
            timeout=kwargs.get("timeout", api_client_timeout),
            **{k: v for k, v in kwargs.items() if k != "timeout"},
        )
    return _openai_clients[cache_key]


def get_genai_client(api_key: str, timeout: float | None = None) -> genai.Client:
    """Get or create a cached Google genai client keyed by api_key and timeout."""
    cache_key = (api_key or "__default__", timeout)
    if cache_key not in _genai_clients:
        http_opts = genai.types.HttpOptions(timeout=int(timeout * 1000)) if timeout else None
        _genai_clients[cache_key] = genai.Client(api_key=api_key or None, http_options=http_opts)
    return _genai_clients[cache_key]


def get_bedrock_client(region: str | None = None) -> Any:
    """Get or create a cached Bedrock runtime client keyed by region.

    Auth is via the Lambda execution role; no API key is required.

    Timeouts are bounded so a Nova call cannot outlive the dispatch budget.
    This client previously used botocore's defaults (60s connect, 60s read,
    legacy retries), which can exceed that budget several times over: the
    request is abandoned, the user is told the model failed, and Bedrock
    generates and bills for the image anyway.

    The read timeout is halved so one retry still fits inside the budget.
    Gemini, OpenAI and Firefly already bound their calls; Nova was the one
    provider left unbounded.
    """
    region_key = region or aws_region
    if region_key not in _bedrock_clients:
        per_attempt = max(1, int(api_client_timeout // 2))
        _bedrock_clients[region_key] = boto3.client(
            "bedrock-runtime",
            region_name=region_key,
            config=BotoConfig(
                connect_timeout=per_attempt,
                read_timeout=per_attempt,
                retries={"mode": "standard", "total_max_attempts": 2},
            ),
        )
    return _bedrock_clients[region_key]
