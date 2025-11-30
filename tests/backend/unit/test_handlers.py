"""
Unit tests for model handlers
"""

import pytest
import responses
from unittest.mock import Mock, patch, MagicMock
from models.handlers import (
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
from .fixtures.api_responses import (
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

        with patch('models.handlers.OpenAI') as mock_openai:
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
            assert result['model'] == 'dall-e-3'
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
        with patch('models.handlers.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            # Simulate API error
            mock_client.images.generate.side_effect = Exception("API Error")

            result = handle_openai(mock_model_config, sample_prompt, sample_params)

            assert result['status'] == 'error'
            assert 'error' in result
            assert 'API Error' in result['error']
            assert result['model'] == 'dall-e-3'

    def test_timeout_handling(self, mock_model_config, sample_prompt, sample_params):
        """Test timeout error handling"""
        with patch('models.handlers.OpenAI') as mock_openai:
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

    def test_gemini_success(self, sample_prompt, sample_params):
        """Test successful Gemini image generation"""
        gemini_config = {
            'index': 1,
            'provider': 'google_gemini',
            'id': 'gemini-2.0-flash-exp',
            'api_key': 'test-gemini-key'
        }

        with patch('models.handlers.genai.Client') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            # Setup mock response with inline_data
            mock_part = Mock()
            mock_part.inline_data = Mock()
            mock_part.inline_data.data = SAMPLE_IMAGE_CONTENT  # bytes

            mock_candidate = Mock()
            mock_candidate.content.parts = [mock_part]

            mock_response = Mock()
            mock_response.candidates = [mock_candidate]

            mock_client.models.generate_content.return_value = mock_response

            result = handle_google_gemini(gemini_config, sample_prompt, sample_params)

            assert result['status'] == 'success'
            assert 'image' in result
            assert result['provider'] == 'google_gemini'

    def test_gemini_error(self, sample_prompt, sample_params):
        """Test Gemini error handling"""
        gemini_config = {
            'index': 1,
            'provider': 'google_gemini',
            'id': 'gemini-2.0-flash-exp',
            'api_key': 'test-gemini-key'
        }

        with patch('models.handlers.genai.Client') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            mock_client.models.generate_content.side_effect = Exception("Gemini API Error")

            result = handle_google_gemini(gemini_config, sample_prompt, sample_params)

            assert result['status'] == 'error'
            assert 'Gemini API Error' in result['error']


class TestBedrockHandlers:
    """Tests for AWS Bedrock handlers"""

    def test_bedrock_nova_success(self, sample_prompt, sample_params):
        """Test successful Nova Canvas generation"""
        nova_config = {
            'index': 1,
            'provider': 'bedrock_nova',
            'id': 'amazon.nova-canvas-v1:0'
        }

        with patch('models.handlers.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client

            # Setup mock response - Nova returns images array
            response_body = f'{{"images": ["{SAMPLE_IMAGE_BASE64}"]}}'
            mock_stream = Mock()
            mock_stream.read.return_value = response_body.encode()
            mock_client.invoke_model.return_value = {'body': mock_stream}

            result = handle_bedrock_nova(nova_config, sample_prompt, sample_params)

            assert result['status'] == 'success'
            assert 'image' in result
            assert result['provider'] == 'bedrock_nova'

    def test_bedrock_sd_success(self, sample_prompt, sample_params):
        """Test successful Bedrock Stable Diffusion generation"""
        sd_config = {
            'index': 1,
            'provider': 'bedrock_sd',
            'id': 'stability.sd3-large-v1:0'
        }

        with patch('models.handlers.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client

            # Setup mock response - SD now returns images array
            response_body = f'{{"images": ["{SAMPLE_IMAGE_BASE64}"]}}'
            mock_stream = Mock()
            mock_stream.read.return_value = response_body.encode()
            mock_client.invoke_model.return_value = {'body': mock_stream}

            result = handle_bedrock_sd(sd_config, sample_prompt, sample_params)

            assert result['status'] == 'success'
            assert 'image' in result
            assert result['provider'] == 'bedrock_sd'


class TestOtherHandlers:
    """Tests for other provider handlers"""

    @responses.activate
    def test_stability_ai_success(self, sample_prompt, sample_params):
        """Test Stability AI handler - returns raw image bytes"""
        stability_config = {
            'index': 1,
            'provider': 'stability',
            'id': 'sd3-large-turbo',
            'api_key': 'test-stability-key'
        }

        # Stability v2beta returns raw image bytes, not JSON
        responses.add(
            responses.POST,
            "https://api.stability.ai/v2beta/stable-image/generate/sd3",
            body=SAMPLE_IMAGE_CONTENT,
            status=200,
            content_type="image/png"
        )

        result = handle_stability(stability_config, sample_prompt, sample_params)

        assert result['status'] == 'success'
        assert 'image' in result
        assert result['provider'] == 'stability'

    @responses.activate
    def test_black_forest_success(self, sample_prompt, sample_params):
        """Test Black Forest Labs handler with polling"""
        bfl_config = {
            'index': 1,
            'provider': 'bfl',
            'id': 'flux-pro-1.1',
            'api_key': 'test-bfl-key'
        }

        # Mock job creation
        responses.add(
            responses.POST,
            "https://api.bfl.ai/v1/flux-pro-1.1",
            json={"id": "test-job-id"},
            status=200
        )

        # Mock polling result (Ready immediately)
        responses.add(
            responses.GET,
            "https://api.bfl.ai/v1/get_result?id=test-job-id",
            json={
                "status": "Ready",
                "result": {"sample": "https://example.com/bfl-image.png"}
            },
            status=200
        )

        # Mock image download
        responses.add(
            responses.GET,
            "https://example.com/bfl-image.png",
            body=SAMPLE_IMAGE_CONTENT,
            status=200
        )

        # Reduce polling parameters to speed up test
        params_with_fast_poll = {**sample_params, 'max_poll_attempts': 1, 'poll_interval_seconds': 0}

        with patch('models.handlers.time.sleep'):  # Skip actual sleeping
            result = handle_bfl(bfl_config, sample_prompt, params_with_fast_poll)

        assert result['status'] == 'success'
        assert 'image' in result
        assert result['provider'] == 'bfl'

    @responses.activate
    def test_recraft_success(self, sample_prompt, sample_params):
        """Test Recraft handler - uses OpenAI SDK"""
        recraft_config = {
            'index': 1,
            'provider': 'recraft',
            'id': 'recraftv3',
            'api_key': 'test-recraft-key'
        }

        # Mock image download
        responses.add(
            responses.GET,
            "https://example.com/recraft-image.png",
            body=SAMPLE_IMAGE_CONTENT,
            status=200
        )

        with patch('models.handlers.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            # Setup mock response
            mock_response = Mock()
            mock_response.data = [Mock(url="https://example.com/recraft-image.png")]
            mock_client.images.generate.return_value = mock_response

            result = handle_recraft(recraft_config, sample_prompt, sample_params)

            assert result['status'] == 'success'
            assert 'image' in result
            assert result['provider'] == 'recraft'

    @responses.activate
    def test_generic_openai_success(self, sample_prompt, sample_params):
        """Test generic OpenAI-compatible handler"""
        generic_config = {
            'index': 1,
            'provider': 'generic',
            'id': 'custom-model',
            'api_key': 'test-generic-key',
            'base_url': 'https://api.example.com'
        }

        # Mock the image download
        responses.add(
            responses.GET,
            "https://example.com/image.png",
            body=SAMPLE_IMAGE_CONTENT,
            status=200
        )

        with patch('models.handlers.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            # Setup mock response
            mock_response = Mock()
            mock_response.data = [Mock(url="https://example.com/image.png")]
            mock_client.images.generate.return_value = mock_response

            result = handle_generic(generic_config, sample_prompt, sample_params)

            assert result['status'] == 'success'
            assert 'image' in result
            assert result['provider'] == 'generic'
