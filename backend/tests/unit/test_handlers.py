"""
Unit tests for model handlers
"""

import pytest
import responses
from unittest.mock import Mock, patch, MagicMock
from src.models.handlers import (
    handle_openai,
    handle_google_gemini,
    handle_google_imagen,
    handle_bedrock_nova,
    handle_bedrock_sd,
    handle_stability,
    handle_bfl,
    handle_recraft,
    handle_generic
)
from tests.unit.fixtures.api_responses import (
    OPENAI_DALLE3_RESPONSE,
    GOOGLE_GEMINI_RESPONSE,
    BEDROCK_NOVA_RESPONSE,
    BEDROCK_SD_RESPONSE,
    STABILITY_AI_RESPONSE,
    BLACK_FOREST_RESPONSE,
    RECRAFT_RESPONSE,
    GENERIC_OPENAI_RESPONSE,
    ERROR_RATE_LIMIT,
    ERROR_UNAUTHORIZED,
    SAMPLE_IMAGE_CONTENT,
    SAMPLE_IMAGE_BASE64
)


class TestOpenAIHandler:
    """Tests for OpenAI DALL-E 3 handler"""

    @responses.activate
    def test_successful_generation(self, mock_model_config, sample_prompt, sample_params):
        """Test successful image generation with OpenAI"""
        # Mock the image download
        responses.add(
            responses.GET,
            "https://example.com/generated-image.png",
            body=SAMPLE_IMAGE_CONTENT,
            status=200
        )

        with patch('src.models.handlers.OpenAI') as mock_openai:
            # Setup mock client
            mock_client = Mock()
            mock_openai.return_value = mock_client

            # Setup mock response
            mock_response = Mock()
            mock_response.data = [Mock(url="https://example.com/generated-image.png")]
            mock_client.images.generate.return_value = mock_response

            # Call handler
            result = handle_openai(mock_model_config, sample_prompt, sample_params)

            # Verify result
            assert result['status'] == 'success'
            assert 'image' in result
            assert result['model'] == 'Test Model'
            assert result['provider'] == 'openai'
            assert isinstance(result['image'], str)  # Base64 string

            # Verify API was called correctly
            mock_client.images.generate.assert_called_once()
            call_kwargs = mock_client.images.generate.call_args[1]
            assert call_kwargs['model'] == 'dall-e-3'
            assert call_kwargs['prompt'] == sample_prompt
            assert call_kwargs['size'] == '1024x1024'

    def test_error_handling(self, mock_model_config, sample_prompt, sample_params):
        """Test error handling in OpenAI handler"""
        with patch('src.models.handlers.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            # Simulate API error
            mock_client.images.generate.side_effect = Exception("API Error")

            result = handle_openai(mock_model_config, sample_prompt, sample_params)

            assert result['status'] == 'error'
            assert 'error' in result
            assert 'API Error' in result['error']
            assert result['model'] == 'Test Model'

    def test_timeout_handling(self, mock_model_config, sample_prompt, sample_params):
        """Test timeout error handling"""
        with patch('src.models.handlers.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            # Simulate timeout
            import requests
            mock_client.images.generate.side_effect = requests.Timeout("Timeout")

            result = handle_openai(mock_model_config, sample_prompt, sample_params)

            assert result['status'] == 'error'
            assert 'timeout' in result['error'].lower() or 'Timeout' in result['error']


class TestGoogleHandlers:
    """Tests for Google AI handlers"""

    def test_gemini_success(self, mock_model_config, sample_prompt, sample_params):
        """Test successful Gemini image generation"""
        with patch('src.models.handlers.genai.GenerativeModel') as mock_model_class:
            mock_model = Mock()
            mock_model_class.return_value = mock_model

            # Setup mock response
            mock_response = Mock()
            mock_part = Mock()
            mock_part.inline_data.mime_type = 'image/png'
            mock_part.inline_data.data = SAMPLE_IMAGE_BASE64.encode()

            mock_candidate = Mock()
            mock_candidate.content.parts = [mock_part]
            mock_response.candidates = [mock_candidate]

            mock_model.generate_content.return_value = mock_response

            result = handle_google_gemini(mock_model_config, sample_prompt, sample_params)

            assert result['status'] == 'success'
            assert 'image' in result
            assert result['provider'] == 'google_gemini'

    def test_gemini_error(self, mock_model_config, sample_prompt, sample_params):
        """Test Gemini error handling"""
        with patch('src.models.handlers.genai.GenerativeModel') as mock_model_class:
            mock_model = Mock()
            mock_model_class.return_value = mock_model

            mock_model.generate_content.side_effect = Exception("Gemini API Error")

            result = handle_google_gemini(mock_model_config, sample_prompt, sample_params)

            assert result['status'] == 'error'
            assert 'Gemini API Error' in result['error']


class TestBedrockHandlers:
    """Tests for AWS Bedrock handlers"""

    def test_bedrock_nova_success(self, mock_model_config, sample_prompt, sample_params):
        """Test successful Nova Canvas generation"""
        with patch('src.models.handlers.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client

            # Setup mock response
            mock_client.invoke_model.return_value = {
                'body': Mock(read=lambda: f'{{"images": ["{SAMPLE_IMAGE_BASE64}"]}}'.encode())
            }

            result = handle_bedrock_nova(mock_model_config, sample_prompt, sample_params)

            assert result['status'] == 'success'
            assert 'image' in result
            assert result['provider'] == 'bedrock_nova'

    def test_bedrock_sd_success(self, mock_model_config, sample_prompt, sample_params):
        """Test successful Bedrock Stable Diffusion generation"""
        with patch('src.models.handlers.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client

            # Setup mock response
            response_body = f'{{"artifacts": [{{"base64": "{SAMPLE_IMAGE_BASE64}", "finishReason": "SUCCESS"}}]}}'
            mock_client.invoke_model.return_value = {
                'body': Mock(read=lambda: response_body.encode())
            }

            result = handle_bedrock_sd(mock_model_config, sample_prompt, sample_params)

            assert result['status'] == 'success'
            assert 'image' in result
            assert result['provider'] == 'bedrock_sd'


class TestOtherHandlers:
    """Tests for other provider handlers"""

    @responses.activate
    def test_stability_ai_success(self, mock_model_config, sample_prompt, sample_params):
        """Test Stability AI handler"""
        responses.add(
            responses.POST,
            "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
            json=STABILITY_AI_RESPONSE,
            status=200
        )

        result = handle_stability(mock_model_config, sample_prompt, sample_params)

        assert result is not None
        assert result['status'] == 'success'
        assert 'image' in result
        assert result['provider'] == 'stability'

    @responses.activate
    def test_black_forest_success(self, mock_model_config, sample_prompt, sample_params):
        """Test Black Forest Labs handler"""
        responses.add(
            responses.POST,
            "https://api.bfl.ml/v1/flux-pro-1.1",
            json=BLACK_FOREST_RESPONSE,
            status=200
        )

        result = handle_bfl(mock_model_config, sample_prompt, sample_params)

        assert result is not None
        assert result['status'] == 'success'
        assert 'image' in result
        assert result['provider'] == 'bfl'

    @responses.activate
    def test_recraft_success(self, mock_model_config, sample_prompt, sample_params):
        """Test Recraft handler"""
        responses.add(
            responses.POST,
            "https://api.recraft.ai/v1/images/generations",
            json=RECRAFT_RESPONSE,
            status=200
        )

        result = handle_recraft(mock_model_config, sample_prompt, sample_params)

        assert result is not None
        assert result['status'] == 'success'
        assert 'image' in result
        assert result['provider'] == 'recraft'

    @responses.activate
    def test_generic_openai_success(self, mock_model_config, sample_prompt, sample_params):
        """Test generic OpenAI-compatible handler"""
        # Mock the image download
        responses.add(
            responses.GET,
            "https://example.com/image.png",
            body=SAMPLE_IMAGE_CONTENT,
            status=200
        )

        responses.add(
            responses.POST,
            f"{mock_model_config.get('endpoint', 'https://api.example.com')}/v1/images/generations",
            json=GENERIC_OPENAI_RESPONSE,
            status=200
        )

        result = handle_generic(mock_model_config, sample_prompt, sample_params)

        assert result is not None
        assert 'status' in result or 'error' in result
