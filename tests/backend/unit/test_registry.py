"""
Unit tests for model registry
"""

import pytest
from unittest.mock import patch
from models.registry import ModelRegistry


class TestModelRegistry:
    """Tests for ModelRegistry class"""

    @patch.dict('os.environ', {
        'MODEL_COUNT': '2',
        'MODEL_1_PROVIDER': 'openai',
        'MODEL_1_ID': 'dall-e-3',
        'MODEL_1_API_KEY': 'openai-key-123',
        'MODEL_2_PROVIDER': 'stability',
        'MODEL_2_ID': 'stable-diffusion-3.5',
        'MODEL_2_API_KEY': 'stability-key-456'
    }, clear=True)
    def test_load_models_from_env(self):
        """Test loading models from environment variables"""
        registry = ModelRegistry()

        assert registry.get_model_count() == 2

        # Get all models and check first one
        models = registry.get_all_models()
        assert len(models) == 2
        model = models[0]
        assert model['id'] == 'dall-e-3'
        assert model['api_key'] == 'openai-key-123'
        assert model['provider'] == 'openai'

    @patch.dict('os.environ', {
        'MODEL_COUNT': '1',
        'MODEL_1_PROVIDER': 'openai',
        'MODEL_1_ID': 'dall-e-3',
        'MODEL_1_API_KEY': 'test-key',
        'PROMPT_MODEL_PROVIDER': 'openai',
        'PROMPT_MODEL_ID': 'gpt-4o',
        'PROMPT_MODEL_API_KEY': 'prompt-key'
    }, clear=True)
    def test_get_prompt_model(self):
        """Test retrieving prompt enhancement model (separate from image models)"""
        registry = ModelRegistry()
        prompt_model = registry.get_prompt_model()

        assert prompt_model is not None
        assert prompt_model['provider'] == 'openai'
        assert prompt_model['id'] == 'gpt-4o'
        assert prompt_model['api_key'] == 'prompt-key'

        # Verify image model is separate
        image_models = registry.get_all_models()
        assert len(image_models) == 1
        assert image_models[0]['id'] == 'dall-e-3'

    @patch.dict('os.environ', {
        'MODEL_COUNT': '2',
        'MODEL_1_PROVIDER': 'openai',
        'MODEL_1_ID': 'dall-e-3',
        'MODEL_1_API_KEY': 'key1',
        'MODEL_2_PROVIDER': 'google_gemini',
        'MODEL_2_ID': 'gemini-2.0-flash-exp',
        'MODEL_2_API_KEY': 'key2'
    }, clear=True)
    def test_get_all_models(self):
        """Test getting all registered models"""
        registry = ModelRegistry()
        all_models = registry.get_all_models()

        assert len(all_models) == 2
        assert all(isinstance(m, dict) for m in all_models)
        assert all('id' in m and 'provider' in m for m in all_models)

    @patch.dict('os.environ', {
        'MODEL_COUNT': '2',
        'MODEL_1_PROVIDER': 'openai',
        'MODEL_1_ID': 'dall-e-3',
        'MODEL_1_API_KEY': 'key1',
        'MODEL_2_PROVIDER': 'google_gemini',
        'MODEL_2_ID': 'gemini-2.0-flash-exp',
        'MODEL_2_API_KEY': 'key2'
    }, clear=True)
    def test_provider_explicit_in_registry(self):
        """Test that registry uses explicit provider from config"""
        registry = ModelRegistry()
        models = registry.get_all_models()

        # First model
        assert models[0]['provider'] == 'openai'

        # Second model
        assert models[1]['provider'] == 'google_gemini'

    @patch.dict('os.environ', {
        'MODEL_COUNT': '0'
    }, clear=True)
    def test_empty_registry(self):
        """Test registry with no models configured"""
        registry = ModelRegistry()

        assert registry.get_model_count() == 0
        assert registry.get_all_models() == []

    @patch.dict('os.environ', {
        'MODEL_COUNT': '1',
        'MODEL_1_PROVIDER': 'generic',
        'MODEL_1_ID': 'custom-model',
        'MODEL_1_API_KEY': 'key1',
        'MODEL_1_BASE_URL': 'https://custom.endpoint.com'
    }, clear=True)
    def test_custom_base_url(self):
        """Test model with custom base URL"""
        registry = ModelRegistry()
        models = registry.get_all_models()

        assert len(models) == 1
        model = models[0]
        assert model['base_url'] == 'https://custom.endpoint.com'
        assert model['provider'] == 'generic'

    @patch.dict('os.environ', {
        'MODEL_COUNT': '1',
        'MODEL_1_PROVIDER': 'openai',
        # Missing MODEL_1_ID intentionally
    }, clear=True)
    def test_invalid_model_config(self):
        """Test handling of invalid model configuration (missing required fields)"""
        registry = ModelRegistry()

        # Registry should skip models missing required fields (provider + id)
        assert registry.get_model_count() == 0

    @patch.dict('os.environ', {
        'MODEL_COUNT': '1',
        'MODEL_1_PROVIDER': 'bedrock_nova',
        'MODEL_1_ID': 'amazon.nova-canvas-v1:0',
        # No API key needed for Bedrock (uses IAM role)
    }, clear=True)
    def test_bedrock_no_api_key(self):
        """Test Bedrock model without API key (uses IAM role)"""
        registry = ModelRegistry()
        models = registry.get_all_models()

        assert len(models) == 1
        model = models[0]
        assert model['provider'] == 'bedrock_nova'
        assert model['id'] == 'amazon.nova-canvas-v1:0'
        assert 'api_key' not in model  # API key not included when empty

    @patch.dict('os.environ', {
        'MODEL_COUNT': '1',
        'MODEL_1_PROVIDER': 'recraft',
        'MODEL_1_ID': 'recraft-v3',
        'MODEL_1_API_KEY': 'recraft-key',
        'MODEL_1_USER_ID': 'user-12345'
    }, clear=True)
    def test_model_with_user_id(self):
        """Test model with user ID field"""
        registry = ModelRegistry()
        models = registry.get_all_models()

        assert len(models) == 1
        model = models[0]
        assert model['user_id'] == 'user-12345'
