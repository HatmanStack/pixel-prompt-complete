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

from config import api_client_timeout, aws_region, generate_dispatch_budget_seconds

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


# Bedrock timeout budget components. botocore applies connect_timeout and
# read_timeout to *separate* phases of one attempt, so a single attempt can
# take up to their sum, and standard retry mode sleeps between attempts.
# The bound is therefore:
#
#   attempts * (connect + read) + backoff <= dispatch budget
#
# not attempts * read. Getting that wrong is how a "bounded" client still
# outlives the budget: at 30s each, two attempts is 120s against a 70s budget.
BEDROCK_MAX_ATTEMPTS = 2
# Connecting to a same-region AWS endpoint from Lambda is sub-second; 5s is
# already generous, and spending the budget on reads is the better trade
# because that is where image generation time actually goes.
BEDROCK_CONNECT_TIMEOUT = 5
# standard retry mode sleeps with exponential backoff plus jitter between
# attempts. One retry is ~1s, but reserve enough that jitter cannot push the
# total past the budget.
BEDROCK_BACKOFF_ALLOWANCE = 5


def bedrock_read_timeout(budget: float) -> int:
    """Largest per-attempt read timeout that keeps the whole call inside ``budget``.

    Derived from the dispatch budget rather than hardcoded so that tuning
    ``API_CLIENT_TIMEOUT`` cannot silently push Nova back over the line.
    """
    per_attempt = (budget - BEDROCK_BACKOFF_ALLOWANCE) / BEDROCK_MAX_ATTEMPTS
    return max(1, int(per_attempt - BEDROCK_CONNECT_TIMEOUT))


def bedrock_worst_case_seconds(budget: float) -> float:
    """Worst-case wall time for a Bedrock call: every attempt maxing out, plus backoff."""
    per_attempt = BEDROCK_CONNECT_TIMEOUT + bedrock_read_timeout(budget)
    return BEDROCK_MAX_ATTEMPTS * per_attempt + BEDROCK_BACKOFF_ALLOWANCE


def get_bedrock_client(region: str | None = None) -> Any:
    """Get or create a cached Bedrock runtime client keyed by region.

    Auth is via the Lambda execution role; no API key is required.

    Timeouts are bounded so a Nova call cannot outlive the dispatch budget.
    This client previously used botocore's defaults (60s connect, 60s read,
    legacy retries), which can exceed that budget several times over: the
    request is abandoned, the user is told the model failed, and Bedrock
    generates and bills for the image anyway.

    Gemini, OpenAI and Firefly already bound their calls; Nova was the one
    provider left unbounded.
    """
    region_key = region or aws_region
    if region_key not in _bedrock_clients:
        _bedrock_clients[region_key] = boto3.client(
            "bedrock-runtime",
            region_name=region_key,
            config=BotoConfig(
                connect_timeout=BEDROCK_CONNECT_TIMEOUT,
                read_timeout=bedrock_read_timeout(generate_dispatch_budget_seconds),
                retries={"mode": "standard", "total_max_attempts": BEDROCK_MAX_ATTEMPTS},
            ),
        )
    return _bedrock_clients[region_key]
