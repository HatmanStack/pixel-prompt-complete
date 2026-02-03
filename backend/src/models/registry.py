"""
Model Registry for Pixel Prompt Complete.

Dynamically loads AI model configurations from environment variables.
No provider detection - users specify provider explicitly.
"""

import os
import warnings
from typing import Dict, List, Optional


class ModelRegistry:
    """
    Registry for managing AI model configurations.

    Loads models from environment variables with explicit provider specification.
    """

    def __init__(self):
        """Initialize the model registry from environment variables."""
        # Load model count for image generation models
        self.model_count = int(os.environ.get('MODEL_COUNT', 9))

        # Load prompt enhancement model (separate from image models)
        prompt_provider = os.environ.get('PROMPT_MODEL_PROVIDER', '')
        prompt_id = os.environ.get('PROMPT_MODEL_ID', '')
        prompt_api_key = os.environ.get('PROMPT_MODEL_API_KEY', '')

        if prompt_provider and prompt_id:
            self.prompt_model: Optional[Dict] = {
                'provider': prompt_provider,
                'id': prompt_id,
            }
            if prompt_api_key:
                self.prompt_model['api_key'] = prompt_api_key
        else:
            self.prompt_model = None
            warnings.warn("Prompt enhancement model not configured (PROMPT_MODEL_PROVIDER/ID missing)")

        # Load image generation models
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

        # Validation - warn if configuration doesn't match
        if len(self.models) != self.model_count:
            warnings.warn(f"MODEL_COUNT={self.model_count} but only {len(self.models)} image models configured")

    def get_prompt_model(self) -> Optional[Dict]:
        """
        Get the model configured for prompt enhancement.

        Returns:
            Model configuration dict for prompt enhancement or None if not configured
        """
        return self.prompt_model

    def get_all_models(self) -> List[Dict]:
        """
        Get all configured models.

        Returns:
            List of model configuration dicts
        """
        return self.models

    def get_model_count(self) -> int:
        """
        Get the number of configured models.

        Returns:
            Number of models
        """
        return len(self.models)
