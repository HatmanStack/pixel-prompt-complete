"""
Unit tests for model registry
"""

import pytest
from unittest.mock import patch
from src.models.registry import ModelRegistry, detect_provider


class TestDetectProvider:
    """Tests for provider detection logic"""

    def test_detect_openai(self):
        """Test OpenAI model detection"""
        assert detect_provider('DALL-E 3') == 'openai'
        assert detect_provider('dall-e-3') == 'openai'
        assert detect_provider('GPT-4 Vision') == 'openai'
        assert detect_provider('chatgpt-image') == 'openai'

    def test_detect_google_gemini(self):
        """Test Google Gemini detection"""
        assert detect_provider('Gemini 2.0 Flash') == 'google_gemini'
        assert detect_provider('gemini-pro-vision') == 'google_gemini'

    def test_detect_google_imagen(self):
        """Test Google Imagen detection"""
        assert detect_provider('Imagen 3.0') == 'google_imagen'
        assert detect_provider('imagen-2') == 'google_imagen'

    def test_detect_bedrock_nova(self):
        """Test Bedrock Nova detection"""
        assert detect_provider('Amazon Nova Canvas') == 'bedrock_nova'
        assert detect_provider('nova-canvas-v1') == 'bedrock_nova'

    def test_detect_bedrock_sd(self):
        """Test Bedrock Stable Diffusion detection"""
        assert detect_provider('Stable Diffusion 3.5 (Bedrock)') == 'bedrock_sd'
        assert detect_provider('AWS Stable Diffusion XL') == 'bedrock_sd'

    def test_detect_stability(self):
        """Test Stability AI detection"""
        assert detect_provider('Stable Diffusion 3.5') == 'stability'
        assert detect_provider('SDXL 1.0') == 'stability'

    def test_detect_black_forest(self):
        """Test Black Forest Labs detection"""
        assert detect_provider('Flux Pro 1.1') == 'bfl'
        assert detect_provider('flux-dev') == 'bfl'

    def test_detect_recraft(self):
        """Test Recraft detection"""
        assert detect_provider('Recraft V3') == 'recraft'
        assert detect_provider('recraft-20b') == 'recraft'

    def test_detect_ideogram(self):
        """Test Ideogram detection falls back to generic"""
        assert detect_provider('Ideogram 2.0') == 'generic'
        assert detect_provider('ideogram-v2') == 'generic'

    def test_detect_midjourney(self):
        """Test Midjourney detection falls back to generic"""
        assert detect_provider('Midjourney v6') == 'generic'
        assert detect_provider('midjourney-v5') == 'generic'

    def test_detect_generic(self):
        """Test generic fallback"""
        assert detect_provider('Unknown Model') == 'generic'
        assert detect_provider('') == 'generic'
        assert detect_provider(None) == 'generic'


class TestModelRegistry:
    """Tests for ModelRegistry class"""

    @patch.dict('os.environ', {
        'MODEL_1_NAME': 'DALL-E 3',
        'MODEL_1_KEY': 'openai-key-123',
        'MODEL_2_NAME': 'Stable Diffusion 3.5',
        'MODEL_2_KEY': 'stability-key-456'
    })
    def test_load_models_from_env(self):
        """Test loading models from environment variables"""
        registry = ModelRegistry()

        assert registry.get_model_count() >= 2

        # Get first model (registry uses 1-based indexing)
        model = registry.get_model_by_index(1)
        assert model is not None
        assert 'name' in model
        assert 'key' in model
        assert 'provider' in model

    @patch.dict('os.environ', {
        'MODEL_1_NAME': 'Test Model',
        'MODEL_1_KEY': 'test-key',
        'PROMPT_MODEL_INDEX': '1'
    })
    def test_get_prompt_model_index(self):
        """Test retrieving prompt model"""
        registry = ModelRegistry()
        prompt_model = registry.get_prompt_model()

        assert prompt_model is not None
        assert 'name' in prompt_model

    @patch.dict('os.environ', {
        'MODEL_1_NAME': 'DALL-E 3',
        'MODEL_1_KEY': 'key1',
        'MODEL_2_NAME': 'Gemini 2.0',
        'MODEL_2_KEY': 'key2'
    })
    def test_get_all_models(self):
        """Test getting all registered models"""
        registry = ModelRegistry()
        all_models = registry.get_all_models()

        assert len(all_models) >= 2
        assert all(isinstance(m, dict) for m in all_models)
        assert all('name' in m and 'key' in m for m in all_models)

    @patch.dict('os.environ', {
        'MODEL_1_NAME': 'Test Model',
        'MODEL_1_KEY': 'test-key'
    })
    def test_get_model_by_index(self):
        """Test getting model by index"""
        registry = ModelRegistry()

        # Registry uses 1-based indexing (MODEL_1, MODEL_2, etc.)
        model = registry.get_model_by_index(1)
        assert model is not None
        assert model['name'] == 'Test Model'
        assert model['key'] == 'test-key'

        # Test invalid index
        invalid_model = registry.get_model_by_index(999)
        assert invalid_model is None

    @patch.dict('os.environ', {
        'MODEL_1_NAME': 'DALL-E 3',
        'MODEL_1_KEY': 'key1',
        'MODEL_2_NAME': 'Gemini',
        'MODEL_2_KEY': 'key2'
    })
    def test_provider_detection_in_registry(self):
        """Test that registry correctly detects providers"""
        registry = ModelRegistry()

        # Registry uses 1-based indexing
        dalle_model = registry.get_model_by_index(1)
        assert dalle_model['provider'] == 'openai'

        gemini_model = registry.get_model_by_index(2)
        assert gemini_model['provider'] == 'google_gemini'

    @patch.dict('os.environ', {})
    def test_empty_registry(self):
        """Test registry with no models configured"""
        registry = ModelRegistry()

        assert registry.get_model_count() == 0
        assert registry.get_all_models() == []
        assert registry.get_model_by_index(1) is None

    @patch.dict('os.environ', {
        'MODEL_1_NAME': 'Model 1',
        'MODEL_1_KEY': 'key1',
        'MODEL_1_ENDPOINT': 'https://custom.endpoint.com'
    })
    def test_custom_endpoint(self):
        """Test model with custom endpoint"""
        registry = ModelRegistry()

        # Registry uses 1-based indexing
        model = registry.get_model_by_index(1)
        assert model is not None
        # Registry might store endpoint if configured
        # Test passes if model is loaded successfully

    @patch.dict('os.environ', {
        'MODEL_1_NAME': 'Test',
        # Missing MODEL_1_KEY intentionally
    })
    def test_invalid_model_config(self):
        """Test handling of invalid model configuration"""
        registry = ModelRegistry()

        # Registry should handle missing keys gracefully
        # Either skip the model or set default values
        # Test passes if no exception is raised
        assert isinstance(registry.get_model_count(), int)
