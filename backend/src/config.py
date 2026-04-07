"""
Configuration module for Pixel Prompt v2.
Loads 4 fixed model configurations with enable/disable support.
"""

import os
import warnings
from dataclasses import dataclass
from typing import Dict, List


def _safe_int(env_var: str, default: int) -> int:
    """Parse int from env var, returning default and warning on bad input."""
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        warnings.warn(
            f"Invalid integer for {env_var}={raw!r}, using default {default}", stacklevel=2
        )
        return default


def _safe_float(env_var: str, default: float) -> float:
    """Parse float from env var, returning default and warning on bad input."""
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        return float(raw)
    except (ValueError, TypeError):
        warnings.warn(f"Invalid float for {env_var}={raw!r}, using default {default}", stacklevel=2)
        return default


@dataclass(frozen=True)
class ModelConfig:
    """Configuration for a single image generation model."""

    name: str  # Internal name: 'flux', 'recraft', 'gemini', 'openai'
    provider: str  # Provider identifier for handler lookup
    enabled: bool
    api_key: str
    model_id: str
    display_name: str  # Human-readable name for UI


# AWS configuration from Lambda execution environment
aws_region = os.environ.get("AWS_REGION", "us-west-2")

# S3 and CloudFront
s3_bucket = os.environ.get("S3_BUCKET")
cloudfront_domain = os.environ.get("CLOUDFRONT_DOMAIN")
if s3_bucket is None:
    warnings.warn("S3_BUCKET not set — storage operations will fail", stacklevel=1)
if cloudfront_domain is None:
    warnings.warn("CLOUDFRONT_DOMAIN not set — CDN URLs will be malformed", stacklevel=1)

# Rate limiting
global_limit = _safe_int("GLOBAL_LIMIT", 1000)
ip_limit = _safe_int("IP_LIMIT", 50)
ip_include_str = os.environ.get("IP_INCLUDE", "")
ip_include = [ip.strip() for ip in ip_include_str.split(",") if ip.strip()]

# Prompt enhancement model configuration
prompt_model_provider = os.environ.get("PROMPT_MODEL_PROVIDER", "openai")
prompt_model_id = os.environ.get("PROMPT_MODEL_ID", "gpt-4o")
prompt_model_api_key = os.environ.get("PROMPT_MODEL_API_KEY", "")

# Firefly OAuth2 credentials (used by adobe_firefly provider)
firefly_client_id = os.environ.get("FIREFLY_CLIENT_ID", "")
firefly_client_secret = os.environ.get("FIREFLY_CLIENT_SECRET", "")

# 4 Fixed Models Configuration
MODELS: Dict[str, ModelConfig] = {
    "gemini": ModelConfig(
        name="gemini",
        provider="google_gemini",
        enabled=os.environ.get("GEMINI_ENABLED", "true").lower() == "true",
        api_key=os.environ.get("GEMINI_API_KEY", ""),
        model_id=os.environ.get("GEMINI_MODEL_ID", "gemini-3.1-flash-image-preview"),
        display_name="Gemini",
    ),
    "nova": ModelConfig(
        name="nova",
        provider="bedrock_nova",
        enabled=os.environ.get("NOVA_ENABLED", "true").lower() == "true",
        api_key="",  # Auth via IAM role
        model_id=os.environ.get("NOVA_MODEL_ID", "amazon.nova-canvas-v1:0"),
        display_name="Nova Canvas",
    ),
    "openai": ModelConfig(
        name="openai",
        provider="openai",
        enabled=os.environ.get("OPENAI_ENABLED", "true").lower() == "true",
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        model_id=os.environ.get("OPENAI_MODEL_ID", "dall-e-3"),
        display_name="DALL-E 3",
    ),
    "firefly": ModelConfig(
        name="firefly",
        provider="adobe_firefly",
        enabled=os.environ.get("FIREFLY_ENABLED", "true").lower() == "true",
        api_key="",  # Auth via OAuth2 client credentials
        model_id=os.environ.get("FIREFLY_MODEL_ID", "firefly-image-5"),
        display_name="Firefly",
    ),
}

# CORS
cors_allowed_origin = os.environ.get("CORS_ALLOWED_ORIGIN", "*")

# Iteration limits
MAX_ITERATIONS = 7
ITERATION_WARNING_THRESHOLD = 5


def get_enabled_models() -> List[ModelConfig]:
    """Return list of enabled ModelConfig objects."""
    return [model for model in MODELS.values() if model.enabled]


def get_model(name: str) -> ModelConfig:
    """
    Get specific model config by name.

    Args:
        name: Model name ('flux', 'recraft', 'gemini', 'openai')

    Returns:
        ModelConfig for the requested model

    Raises:
        ValueError: If model name is invalid or model is disabled
    """
    if name not in MODELS:
        raise ValueError(f"Unknown model: {name}. Valid models: {list(MODELS.keys())}")

    model = MODELS[name]
    if not model.enabled:
        raise ValueError(f"Model '{name}' is disabled")

    return model


def get_model_config_dict(model: ModelConfig) -> Dict:
    """
    Convert ModelConfig to dict format expected by handlers.

    Returns:
        Dict with 'id', 'api_key', and provider-specific fields
    """
    config = {
        "id": model.model_id,
        "provider": model.provider,
    }
    config["api_key"] = model.api_key
    if model.provider == "adobe_firefly":
        config["client_id"] = firefly_client_id
        config["client_secret"] = firefly_client_secret
    return config


# Operational Timeouts (seconds) - configurable via environment
api_client_timeout = _safe_float("API_CLIENT_TIMEOUT", 120.0)
image_download_timeout = _safe_int("IMAGE_DOWNLOAD_TIMEOUT", 30)
generate_thread_workers = _safe_int("GENERATE_THREAD_WORKERS", 4)
