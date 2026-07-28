"""
Cached SDK client factories for Lambda container reuse.

Provides singleton clients keyed by API key (and relevant kwargs)
so that repeated calls within the same Lambda invocation reuse
the same HTTP connection pool.
"""

import threading
from typing import Any, Dict

import boto3
from botocore.config import Config as BotoConfig
from google import genai
from openai import OpenAI

from config import api_client_timeout, aws_region, generate_dispatch_budget_seconds

# Module-level client singletons for Lambda container reuse.
#
# Four generation threads read and write these. The race is benign in
# OUTCOME -- two threads missing a cold cache both construct a client and one
# connection pool is discarded, not a wrong client returned -- so the lock is
# not buying correctness so much as consistency: models/providers/firefly.py
# guards its equivalent token cache with an explicit threading.Lock, and two
# caches in one codebase following different patterns is itself a defect,
# because the next reader cannot tell which one is intended. That is worth
# more than the microseconds.
#
# Double-checked on the way in: the common case is a warm cache and takes no
# lock at all.
_openai_clients: Dict[Any, OpenAI] = {}
_genai_clients: Dict[Any, genai.Client] = {}
_bedrock_clients: Dict[Any, Any] = {}
_openai_lock = threading.Lock()
_genai_lock = threading.Lock()
_bedrock_lock = threading.Lock()


def get_openai_client(api_key: str, **kwargs: Any) -> OpenAI:
    """Get or create a cached OpenAI client keyed by api_key and relevant kwargs.

    Note: The cache key only includes ``base_url`` and ``timeout``.  If a new kwarg
    is added to callers that affects client behaviour, it **must** be added to the
    ``_CACHE_KEY_KWARGS`` set below to avoid returning a stale cached client.

    ``max_retries`` is pinned rather than left at the SDK default of 2. The
    default makes the configured timeout a per-attempt bound, so a 60s timeout
    is really a 180s worst case -- and inside a fixed budget a retry is never
    free, it is paid for by shortening the attempt that matters. See
    ``OPENAI_MAX_ATTEMPTS``.
    """
    _CACHE_KEY_KWARGS = ("base_url", "timeout")
    _CACHE_KEY_DEFAULTS = {"timeout": api_client_timeout}
    normalized = {k: kwargs.get(k, _CACHE_KEY_DEFAULTS.get(k)) for k in _CACHE_KEY_KWARGS}
    extra = tuple(sorted((k, v) for k, v in normalized.items() if v is not None))
    cache_key = (api_key or "__default__", extra)
    if cache_key not in _openai_clients:
        with _openai_lock:
            if cache_key not in _openai_clients:
                _openai_clients[cache_key] = OpenAI(
                    api_key=api_key or None,
                    timeout=kwargs.get("timeout", api_client_timeout),
                    max_retries=OPENAI_MAX_ATTEMPTS - 1,
                    **{k: v for k, v in kwargs.items() if k != "timeout"},
                )
    return _openai_clients[cache_key]


def get_genai_client(api_key: str, timeout: float | None = None) -> genai.Client:
    """Get or create a cached Google genai client keyed by api_key and timeout."""
    cache_key = (api_key or "__default__", timeout)
    if cache_key not in _genai_clients:
        with _genai_lock:
            if cache_key not in _genai_clients:
                http_opts = (
                    genai.types.HttpOptions(timeout=int(timeout * 1000)) if timeout else None
                )
                _genai_clients[cache_key] = genai.Client(
                    api_key=api_key or None, http_options=http_opts
                )
    return _genai_clients[cache_key]


# ---------------------------------------------------------------------------
# Per-provider worst-case bounds
#
# config.py states the invariant: every provider must bound its own call below
# the dispatch budget, because the dispatch timeout cannot cancel a future that
# has already started. The bound a provider needs is not its own timeout, it is
# the sum over every sequential call it makes multiplied by every attempt it
# may make -- which is why a "bounded" 60s Firefly client still ran ~190s.
#
# Each provider therefore gets two functions with the same contract:
#
#   <p>_call_timeout(budget)       -> the per-call timeout to configure
#   <p>_worst_case_seconds(budget) -> the wall time that configuration permits
#
# and ``<p>_worst_case_seconds(b) <= b`` is asserted for all four in
# tests/backend/unit/test_provider_timeouts.py.
# ---------------------------------------------------------------------------

# Gemini returns the image inline on a single generate_content call, and the
# google-genai client is not configured to retry, so its worst case is simply
# the timeout it is handed.
GEMINI_SEQUENTIAL_CALLS = 1


def gemini_call_timeout(budget: float) -> float:
    """Per-call timeout for Gemini: the whole budget, since there is one call."""
    return max(1.0, float(budget))


def gemini_worst_case_seconds(budget: float) -> float:
    """Worst-case wall time for a Gemini call."""
    return GEMINI_SEQUENTIAL_CALLS * gemini_call_timeout(budget)


# OpenAI's chain is the SDK call and then our own download of the returned
# URL -- two sequential calls, not one. The download is not free, and counting
# it as free is how the budget was overrun on the OpenAI path too.
OPENAI_SEQUENTIAL_CALLS = 2
# The SDK retries twice by default, which silently turns the configured
# timeout into a per-attempt bound: 60s becomes a 180s worst case. Inside a
# fixed budget a retry is paid for by shortening the attempt that matters, and
# an image generation that needs more than the shortened slice fails every
# attempt rather than one. One attempt with the full slice is the better trade.
OPENAI_MAX_ATTEMPTS = 1


def openai_call_timeout(budget: float) -> int:
    """Per-call timeout that keeps the OpenAI chain inside ``budget``."""
    slots = OPENAI_MAX_ATTEMPTS + (OPENAI_SEQUENTIAL_CALLS - 1)
    return max(1, int(budget / slots))


def openai_worst_case_seconds(budget: float) -> float:
    """Worst-case wall time for the OpenAI chain: every attempt, plus the download."""
    slots = OPENAI_MAX_ATTEMPTS + (OPENAI_SEQUENTIAL_CALLS - 1)
    return slots * openai_call_timeout(budget)


# Firefly's slowest path is outpaint: token, storage upload, expand, image
# download -- four sequential HTTP calls, not one. ``requests`` applies its
# timeout per call, so the bound is the sum, and the hardcoded 60s that used
# to sit on three of those four calls was ~190s against a 70s budget.
FIREFLY_SEQUENTIAL_CALLS = 4
# The token call is an auth round trip rather than image generation, so it
# keeps a short fixed timeout instead of an equal share. It is still counted
# in the worst case: a blocking call that cannot be cancelled costs its
# timeout whatever the call is for.
FIREFLY_TOKEN_TIMEOUT = 10


def firefly_call_timeout(budget: float) -> int:
    """Per-call timeout that keeps the whole Firefly chain inside ``budget``."""
    remaining = budget - FIREFLY_TOKEN_TIMEOUT
    return max(1, int(remaining / (FIREFLY_SEQUENTIAL_CALLS - 1)))


def firefly_worst_case_seconds(budget: float) -> float:
    """Worst-case wall time for the longest Firefly path (outpaint)."""
    return FIREFLY_TOKEN_TIMEOUT + (FIREFLY_SEQUENTIAL_CALLS - 1) * firefly_call_timeout(budget)


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


def get_bedrock_client(region: str | None = None, budget: float | None = None) -> Any:
    """Get or create a cached Bedrock runtime client keyed by region and budget.

    Auth is via the Lambda execution role; no API key is required.

    Timeouts are bounded so a Nova call cannot outlive the budget that binds
    it. This client previously used botocore's defaults (60s connect, 60s
    read, legacy retries), which can exceed that budget several times over:
    the request is abandoned, the user is told the model failed, and Bedrock
    generates and bills for the image anyway.

    ``budget`` defaults to the asynchronous dispatch budget. ``/iterate`` and
    ``/outpaint`` pass the smaller synchronous one, which is why it is part of
    the cache key: handing back the 70s-budget client on a 25s path would
    return a client bounded for a ceiling that does not apply to it.

    What each provider is bounded by -- this docstring used to claim Gemini,
    OpenAI and Firefly were already bounded, and Firefly was not:

    * Gemini  -- one call, timeout via ``HttpOptions`` (``gemini_call_timeout``)
    * Nova    -- attempts x (connect + read) + backoff, below
    * OpenAI  -- SDK call plus image download, retries pinned
                 (``openai_call_timeout``)
    * Firefly -- token + upload + generate/expand + download
                 (``firefly_call_timeout``); it was the unbounded one
    """
    region_key = region or aws_region
    budget_key = generate_dispatch_budget_seconds if budget is None else budget
    cache_key = (region_key, budget_key)
    if cache_key not in _bedrock_clients:
        with _bedrock_lock:
            if cache_key not in _bedrock_clients:
                _bedrock_clients[cache_key] = boto3.client(
                    "bedrock-runtime",
                    region_name=region_key,
                    config=BotoConfig(
                        connect_timeout=BEDROCK_CONNECT_TIMEOUT,
                        read_timeout=bedrock_read_timeout(budget_key),
                        retries={
                            "mode": "standard",
                            "total_max_attempts": BEDROCK_MAX_ATTEMPTS,
                        },
                    ),
                )
    return _bedrock_clients[cache_key]


# Every provider's worst case, keyed by the ``provider`` field on
# ``config.ModelConfig``. A fifth provider added without an entry here fails
# test_provider_timeouts.py rather than shipping unbounded, which is the only
# mechanism that stops the Firefly defect recurring under a different name.
PROVIDER_WORST_CASE = {
    "google_gemini": gemini_worst_case_seconds,
    "bedrock_nova": bedrock_worst_case_seconds,
    "openai": openai_worst_case_seconds,
    "adobe_firefly": firefly_worst_case_seconds,
}
