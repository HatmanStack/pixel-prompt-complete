"""
Model Registry for Pixel Prompt Complete.

Dynamically loads AI model configurations from environment variables
and provides intelligent provider detection based on model names.
"""

import os
from typing import List, Dict, Optional


def detect_provider(model_name: str) -> str:
    """
    Detect AI provider from model name using pattern matching.

    Args:
        model_name: Name of the AI model

    Returns:
        Provider identifier string (e.g., 'openai', 'google_gemini', 'generic')
    """
    if not model_name:
        return 'generic'

    name_lower = model_name.lower()

    # OpenAI models
    if any(keyword in name_lower for keyword in ['dalle', 'dall-e', 'gpt', 'chatgpt']):
        return 'openai'

    # Google Gemini
    if 'gemini' in name_lower:
        return 'google_gemini'

    # Google Imagen
    if 'imagen' in name_lower:
        return 'google_imagen'

    # AWS Bedrock - Nova Canvas
    if any(keyword in name_lower for keyword in ['nova', 'amazon nova']):
        return 'bedrock_nova'

    # AWS Bedrock - Stable Diffusion
    if any(keyword in name_lower for keyword in ['stable diffusion', 'sd3', 'sdxl']) and \
       any(keyword in name_lower for keyword in ['bedrock', 'aws', 'amazon']):
        return 'bedrock_sd'

    # Stability AI (non-Bedrock)
    if any(keyword in name_lower for keyword in ['stability', 'stable diffusion', 'sd ', 'sdxl']):
        return 'stability'

    # Black Forest Labs (Flux)
    if any(keyword in name_lower for keyword in ['flux', 'black forest', 'bfl']):
        return 'bfl'

    # Recraft
    if 'recraft' in name_lower:
        return 'recraft'

    # Hunyuan
    if 'hunyuan' in name_lower:
        return 'hunyuan'

    # Qwen
    if 'qwen' in name_lower:
        return 'qwen'

    # Default fallback
    print(f"Unknown provider for model '{model_name}', using generic handler")
    return 'generic'


class ModelRegistry:
    """
    Registry for managing AI model configurations.

    Loads models from environment variables and provides access methods
    for model lookup and prompt enhancement configuration.
    """

    def __init__(self):
        """Initialize the model registry from environment variables."""
        # Load model count
        self.model_count = int(os.environ.get('MODEL_COUNT', 9))
        self.prompt_model_index = int(os.environ.get('PROMPT_MODEL_INDEX', 1))

        # Load all models
        self.models: List[Dict] = []
        for i in range(1, self.model_count + 1):
            name = os.environ.get(f'MODEL_{i}_NAME')
            key = os.environ.get(f'MODEL_{i}_KEY')

            # Only add if both name and key are provided
            if name and key:
                provider = detect_provider(name)
                self.models.append({
                    'index': i,
                    'name': name,
                    'key': key,
                    'provider': provider
                })
                print(f"Loaded model {i}: {name} (provider: {provider})")

        # Validation
        if len(self.models) != self.model_count:
            print(f"Warning: MODEL_COUNT is {self.model_count} but only "
                  f"{len(self.models)} models are configured")

        if self.prompt_model_index < 1 or self.prompt_model_index > len(self.models):
            print(f"Warning: PROMPT_MODEL_INDEX {self.prompt_model_index} is out of "
                  f"range (1-{len(self.models)})")

        print(f"Model registry initialized with {len(self.models)} models")

    def get_model_by_index(self, index: int) -> Optional[Dict]:
        """
        Get model configuration by 1-based index.

        Args:
            index: 1-based index of the model

        Returns:
            Model configuration dict or None if not found
        """
        for model in self.models:
            if model['index'] == index:
                return model
        return None

    def get_prompt_model(self) -> Optional[Dict]:
        """
        Get the model configured for prompt enhancement.

        Returns:
            Model configuration dict for prompt enhancement or None if not found
        """
        return self.get_model_by_index(self.prompt_model_index)

    def get_all_models(self) -> List[Dict]:
        """
        Get all configured models.

        Returns:
            List of model configuration dicts
        """
        return self.models

    def get_models_by_provider(self, provider: str) -> List[Dict]:
        """
        Get all models for a specific provider.

        Args:
            provider: Provider identifier (e.g., 'openai', 'google_gemini')

        Returns:
            List of model configuration dicts for the provider
        """
        return [model for model in self.models if model['provider'] == provider]

    def get_model_count(self) -> int:
        """
        Get the number of configured models.

        Returns:
            Number of models
        """
        return len(self.models)

    def __repr__(self) -> str:
        """String representation of the registry."""
        return f"ModelRegistry({len(self.models)} models configured)"
