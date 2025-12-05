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

        # Get first model (registry uses 1-based indexing)
        model = registry.get_model_by_index(1)
        assert model is not None
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
        image_model = registry.get_model_by_index(1)
        assert image_model['id'] == 'dall-e-3'

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
        'MODEL_COUNT': '1',
        'MODEL_1_PROVIDER': 'bfl',
        'MODEL_1_ID': 'flux-pro-1.1',
        'MODEL_1_API_KEY': 'test-key'
    }, clear=True)
    def test_get_model_by_index(self):
        """Test getting model by index"""
        registry = ModelRegistry()

        # Registry uses 1-based indexing (MODEL_1, MODEL_2, etc.)
        model = registry.get_model_by_index(1)
        assert model is not None
        assert model['id'] == 'flux-pro-1.1'
        assert model['api_key'] == 'test-key'
        assert model['provider'] == 'bfl'

        # Test invalid index
        invalid_model = registry.get_model_by_index(999)
        assert invalid_model is None

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

        # Registry uses 1-based indexing
        dalle_model = registry.get_model_by_index(1)
        assert dalle_model['provider'] == 'openai'

        gemini_model = registry.get_model_by_index(2)
        assert gemini_model['provider'] == 'google_gemini'

    @patch.dict('os.environ', {
        'MODEL_COUNT': '0'
    }, clear=True)
    def test_empty_registry(self):
        """Test registry with no models configured"""
        registry = ModelRegistry()

        assert registry.get_model_count() == 0
        assert registry.get_all_models() == []
        assert registry.get_model_by_index(1) is None

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

        # Registry uses 1-based indexing
        model = registry.get_model_by_index(1)
        assert model is not None
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

        model = registry.get_model_by_index(1)
        assert model is not None
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

        model = registry.get_model_by_index(1)
        assert model is not None
        assert model['user_id'] == 'user-12345'

    @patch.dict('os.environ', {
        'MODEL_COUNT': '2',
        'MODEL_1_PROVIDER': 'openai',
        'MODEL_1_ID': 'dall-e-3',
        'MODEL_1_API_KEY': 'key1',
        'MODEL_2_PROVIDER': 'openai',
        'MODEL_2_ID': 'dall-e-2',
        'MODEL_2_API_KEY': 'key2'
    }, clear=True)
    def test_get_models_by_provider(self):
        """Test filtering models by provider"""
        registry = ModelRegistry()

        openai_models = registry.get_models_by_provider('openai')
        assert len(openai_models) == 2

        google_models = registry.get_models_by_provider('google_gemini')
        assert len(google_models) == 0
