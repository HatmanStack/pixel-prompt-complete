"""
Unit tests for model handlers
"""

import pytest
import responses
from unittest.mock import Mock, patch, MagicMock
from models.handlers import (
    handle_openai,
    handle_google_gemini,
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

        with patch('utils.clients.OpenAI') as mock_openai:
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
        with patch('utils.clients.OpenAI') as mock_openai:
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
        with patch('utils.clients.OpenAI') as mock_openai:
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

        with patch('utils.clients.genai.Client') as mock_client_class:
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

        with patch('utils.clients.genai.Client') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            mock_client.models.generate_content.side_effect = Exception("Gemini API Error")

            result = handle_google_gemini(gemini_config, sample_prompt, sample_params)

            assert result['status'] == 'error'
            assert 'Gemini API Error' in result['error']
