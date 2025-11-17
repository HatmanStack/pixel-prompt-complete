"""
Model Registry for Pixel Prompt Complete.

Dynamically loads AI model configurations from environment variables.
No provider detection - users specify provider explicitly.
"""

import os
from typing import List, Dict, Optional


class ModelRegistry:
    """
    Registry for managing AI model configurations.

    Loads models from environment variables with explicit provider specification.
    """

    def __init__(self):
        """Initialize the model registry from environment variables."""
        # Load model count
        self.model_count = int(os.environ.get('MODEL_COUNT', 9))
        self.prompt_model_index = int(os.environ.get('PROMPT_MODEL_INDEX', 1))

        # Load all models
        self.models: List[Dict] = []
        for i in range(1, self.model_count + 1):
            provider = os.environ.get(f'MODEL_{i}_PROVIDER', '')
            model_id = os.environ.get(f'MODEL_{i}_ID', '')
            api_key = os.environ.get(f'MODEL_{i}_API_KEY', '')
            base_url = os.environ.get(f'MODEL_{i}_BASE_URL', '')
            user_id = os.environ.get(f'MODEL_{i}_USER_ID', '')

            # Only add if provider and model ID are provided
            if provider and model_id:
                model_config = {
                    'index': i,
                    'provider': provider,
                    'id': model_id,
                }

                # Only include optional fields if they're not empty
                if api_key:
                    model_config['api_key'] = api_key
                if base_url:
                    model_config['base_url'] = base_url
                if user_id:
                    model_config['user_id'] = user_id

                self.models.append(model_config)
                print(f"Loaded model {i}: {model_id} (provider: {provider})")

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
