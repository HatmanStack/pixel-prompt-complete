"""
Configuration module for Pixel Prompt v2.
Loads 4 fixed model configurations with enable/disable support.
"""

import os
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ModelConfig:
    """Configuration for a single image generation model."""
    name: str           # Internal name: 'flux', 'recraft', 'gemini', 'openai'
    provider: str       # Provider identifier for handler lookup
    enabled: bool
    api_key: str
    model_id: str
    display_name: str   # Human-readable name for UI


# AWS configuration from Lambda execution environment
aws_region = os.environ.get('AWS_REGION', 'us-west-2')

# Bedrock-specific regions (some models require specific regions)
bedrock_nova_region = os.environ.get('BEDROCK_NOVA_REGION', 'us-east-1')
bedrock_sd_region = os.environ.get('BEDROCK_SD_REGION', 'us-west-2')

# S3 and CloudFront
s3_bucket = os.environ.get('S3_BUCKET')
cloudfront_domain = os.environ.get('CLOUDFRONT_DOMAIN')

# Rate limiting
global_limit = int(os.environ.get('GLOBAL_LIMIT', 1000))
ip_limit = int(os.environ.get('IP_LIMIT', 50))
ip_include_str = os.environ.get('IP_INCLUDE', '')
ip_include = [ip.strip() for ip in ip_include_str.split(',') if ip.strip()]

# Prompt enhancement model configuration
prompt_model_provider = os.environ.get('PROMPT_MODEL_PROVIDER', 'openai')
prompt_model_id = os.environ.get('PROMPT_MODEL_ID', 'gpt-4o')
prompt_model_api_key = os.environ.get('PROMPT_MODEL_API_KEY', '')

# 4 Fixed Models Configuration
MODELS: Dict[str, ModelConfig] = {
    'flux': ModelConfig(
        name='flux',
        provider='bfl',
        enabled=os.environ.get('FLUX_ENABLED', 'true').lower() == 'true',
        api_key=os.environ.get('FLUX_API_KEY', ''),
        model_id=os.environ.get('FLUX_MODEL_ID', 'flux-pro-1.1'),
        display_name='Flux'
    ),
    'recraft': ModelConfig(
        name='recraft',
        provider='recraft',
        enabled=os.environ.get('RECRAFT_ENABLED', 'true').lower() == 'true',
        api_key=os.environ.get('RECRAFT_API_KEY', ''),
        model_id=os.environ.get('RECRAFT_MODEL_ID', 'recraftv3'),
        display_name='Recraft'
    ),
    'gemini': ModelConfig(
        name='gemini',
        provider='google_gemini',
        enabled=os.environ.get('GEMINI_ENABLED', 'true').lower() == 'true',
        api_key=os.environ.get('GEMINI_API_KEY', ''),
        model_id=os.environ.get('GEMINI_MODEL_ID', 'gemini-2.0-flash-exp'),
        display_name='Gemini'
    ),
    'openai': ModelConfig(
        name='openai',
        provider='openai',
        enabled=os.environ.get('OPENAI_ENABLED', 'true').lower() == 'true',
        api_key=os.environ.get('OPENAI_API_KEY', ''),
        model_id=os.environ.get('OPENAI_MODEL_ID', 'gpt-image-1'),
        display_name='OpenAI'
    ),
}

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


def is_model_enabled(name: str) -> bool:
    """Check if a model is enabled."""
    if name not in MODELS:
        return False
    return MODELS[name].enabled


def get_model_config_dict(model: ModelConfig) -> Dict:
    """
    Convert ModelConfig to dict format expected by handlers.

    Returns:
        Dict with 'id', 'api_key', and provider-specific fields
    """
    config = {
        'id': model.model_id,
        'provider': model.provider,
    }
    if model.api_key:
        config['api_key'] = model.api_key
    return config


# Model order for UI display (fixed order)
MODEL_ORDER = ['flux', 'recraft', 'gemini', 'openai']

# Operational Timeouts (seconds) - configurable via environment
api_client_timeout = float(os.environ.get('API_CLIENT_TIMEOUT', '120.0'))
image_download_timeout = int(os.environ.get('IMAGE_DOWNLOAD_TIMEOUT', '30'))
handler_timeout = int(os.environ.get('HANDLER_TIMEOUT', '180'))
max_thread_workers = int(os.environ.get('MAX_THREAD_WORKERS', '10'))
generate_thread_workers = int(os.environ.get('GENERATE_THREAD_WORKERS', '4'))

# BFL polling configuration
bfl_max_poll_attempts = int(os.environ.get('BFL_MAX_POLL_ATTEMPTS', '40'))
bfl_poll_interval = int(os.environ.get('BFL_POLL_INTERVAL', '3'))
