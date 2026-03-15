"""
Cached SDK client factories for Lambda container reuse.

Provides singleton clients keyed by API key (and relevant kwargs)
so that repeated calls within the same Lambda invocation reuse
the same HTTP connection pool.
"""

from typing import Any, Dict

from google import genai
from openai import OpenAI

from config import api_client_timeout

# Module-level client singletons for Lambda container reuse
_openai_clients: Dict[Any, OpenAI] = {}
_genai_clients: Dict[str, genai.Client] = {}


def get_openai_client(api_key: str, **kwargs) -> OpenAI:
    """Get or create a cached OpenAI client keyed by api_key and relevant kwargs."""
    extra = tuple(sorted((k, v) for k, v in kwargs.items() if k in ('base_url', 'timeout')))
    cache_key = (api_key or '__default__', extra)
    if cache_key not in _openai_clients:
        _openai_clients[cache_key] = OpenAI(
            api_key=api_key or None,
            timeout=kwargs.get('timeout', api_client_timeout),
            **{k: v for k, v in kwargs.items() if k != 'timeout'},
        )
    return _openai_clients[cache_key]


def get_genai_client(api_key: str) -> genai.Client:
    """Get or create a cached Google genai client keyed by api_key."""
    cache_key = api_key or '__default__'
    if cache_key not in _genai_clients:
        _genai_clients[cache_key] = genai.Client(api_key=api_key or None)
    return _genai_clients[cache_key]
