"""
Unit tests for iteration handlers.

Tests for get_iterate_handler dispatcher and individual iterate_* functions
for each provider (bfl, recraft, google_gemini, openai).
"""

import pytest
import responses
import base64
from unittest.mock import Mock, patch, MagicMock
from models.handlers import (
    get_iterate_handler,
    iterate_flux,
    iterate_recraft,
    iterate_gemini,
    iterate_openai,
)
from .fixtures.api_responses import (
    SAMPLE_IMAGE_CONTENT,
    SAMPLE_IMAGE_BASE64
)


class TestGetIterateHandler:
    """Tests for get_iterate_handler dispatcher function."""

    def test_returns_flux_handler_for_bfl(self):
        """Test get_iterate_handler returns correct handler for BFL provider."""
        handler = get_iterate_handler('bfl')
        assert handler == iterate_flux

    def test_returns_recraft_handler(self):
        """Test get_iterate_handler returns correct handler for Recraft provider."""
        handler = get_iterate_handler('recraft')
        assert handler == iterate_recraft

    def test_returns_gemini_handler(self):
        """Test get_iterate_handler returns correct handler for Google Gemini."""
        handler = get_iterate_handler('google_gemini')
        assert handler == iterate_gemini

    def test_returns_openai_handler(self):
        """Test get_iterate_handler returns correct handler for OpenAI."""
        handler = get_iterate_handler('openai')
        assert handler == iterate_openai

    def test_raises_for_unknown_provider(self):
        """Test get_iterate_handler raises ValueError for unknown provider."""
        with pytest.raises(ValueError) as exc_info:
            get_iterate_handler('unknown_provider')
        assert 'No iteration handler' in str(exc_info.value)
        assert 'unknown_provider' in str(exc_info.value)


class TestIterateFlux:
    """Tests for iterate_flux handler."""

    @pytest.fixture
    def flux_config(self):
        return {
            'provider': 'bfl',
            'id': 'flux-pro-1.1-fill',
            'api_key': 'test-bfl-key'
        }

    @pytest.fixture
    def sample_context(self):
        return [
            {'iteration': 0, 'prompt': 'original prompt', 'image_key': 'test/0.png'},
            {'iteration': 1, 'prompt': 'first edit', 'image_key': 'test/1.png'},
        ]

    @responses.activate
    def test_successful_iteration(self, flux_config, sample_context):
        """Test successful image iteration with Flux Fill API."""
        # Mock job creation
        responses.add(
            responses.POST,
            "https://api.bfl.ai/v1/flux-pro-1.1-fill",
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

        with patch('models.handlers.time.sleep'):  # Skip actual sleeping
            result = iterate_flux(
                flux_config,
                SAMPLE_IMAGE_BASE64,
                "make the sky purple",
                sample_context
            )

        assert result['status'] == 'success'
        assert 'image' in result
        assert result['provider'] == 'bfl'

    @responses.activate
    def test_handles_api_error(self, flux_config, sample_context):
        """Test error handling when Flux API fails."""
        responses.add(
            responses.POST,
            "https://api.bfl.ai/v1/flux-pro-1.1-fill",
            json={"error": "Invalid request"},
            status=400
        )

        result = iterate_flux(
            flux_config,
            SAMPLE_IMAGE_BASE64,
            "make the sky purple",
            sample_context
        )

        assert result['status'] == 'error'
        assert 'error' in result
        assert result['provider'] == 'bfl'

    def test_builds_context_prompt(self, flux_config):
        """Test that context is incorporated into the prompt."""
        context = [
            {'iteration': 0, 'prompt': 'a sunset'},
            {'iteration': 1, 'prompt': 'add mountains'},
        ]

        # We can't easily test internal prompt building without mocking,
        # but we can verify the handler accepts context without error
        with patch('models.handlers.requests.post') as mock_post:
            mock_post.return_value.json.return_value = {"id": "test-id"}
            mock_post.return_value.status_code = 200

            # This will fail at polling but we just want to verify
            # context is processed without error
            try:
                iterate_flux(
                    flux_config,
                    SAMPLE_IMAGE_BASE64,
                    "make it darker",
                    context
                )
            except Exception:
                pass  # Expected to fail at polling

            # Verify POST was called
            assert mock_post.called


class TestIterateRecraft:
    """Tests for iterate_recraft handler."""

    @pytest.fixture
    def recraft_config(self):
        return {
            'provider': 'recraft',
            'id': 'recraftv3',
            'api_key': 'test-recraft-key'
        }

    @pytest.fixture
    def sample_context(self):
        return [
            {'iteration': 0, 'prompt': 'a cat', 'image_key': 'test/0.png'},
        ]

    @responses.activate
    def test_successful_iteration(self, recraft_config, sample_context):
        """Test successful image iteration with Recraft imageToImage endpoint."""
        # Mock the Recraft API endpoint
        responses.add(
            responses.POST,
            "https://external.api.recraft.ai/v1/images/imageToImage",
            json={"data": [{"url": "https://example.com/recraft-result.png"}]},
            status=200
        )

        # Mock image download
        responses.add(
            responses.GET,
            "https://example.com/recraft-result.png",
            body=SAMPLE_IMAGE_CONTENT,
            status=200
        )

        result = iterate_recraft(
            recraft_config,
            SAMPLE_IMAGE_BASE64,
            "make the cat orange",
            sample_context
        )

        assert result['status'] == 'success'
        assert 'image' in result
        assert result['provider'] == 'recraft'

    @responses.activate
    def test_handles_api_error(self, recraft_config, sample_context):
        """Test error handling when Recraft API fails."""
        responses.add(
            responses.POST,
            "https://external.api.recraft.ai/v1/images/imageToImage",
            json={"error": "API Error"},
            status=500
        )

        result = iterate_recraft(
            recraft_config,
            SAMPLE_IMAGE_BASE64,
            "make the cat orange",
            sample_context
        )

        assert result['status'] == 'error'
        assert 'error' in result
        assert result['provider'] == 'recraft'


class TestIterateGemini:
    """Tests for iterate_gemini handler."""

    @pytest.fixture
    def gemini_config(self):
        return {
            'provider': 'google_gemini',
            'id': 'gemini-2.0-flash-exp',
            'api_key': 'test-gemini-key'
        }

    @pytest.fixture
    def sample_context(self):
        return [
            {'iteration': 0, 'prompt': 'a landscape', 'image_key': 'test/0.png'},
            {'iteration': 1, 'prompt': 'add trees', 'image_key': 'test/1.png'},
        ]

    def test_successful_iteration(self, gemini_config, sample_context):
        """Test successful image iteration with Gemini."""
        with patch('models.handlers.genai.Client') as mock_client_class, \
             patch('models.handlers.types') as mock_types:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            # Mock types.Part methods
            mock_types.Part.from_bytes.return_value = Mock()
            mock_types.Part.from_text.return_value = Mock()
            mock_types.GenerateContentConfig.return_value = Mock()

            # Setup mock response with inline_data
            mock_part = Mock()
            mock_part.inline_data = Mock()
            mock_part.inline_data.data = SAMPLE_IMAGE_CONTENT

            mock_candidate = Mock()
            mock_candidate.content.parts = [mock_part]

            mock_response = Mock()
            mock_response.candidates = [mock_candidate]

            mock_client.models.generate_content.return_value = mock_response

            result = iterate_gemini(
                gemini_config,
                SAMPLE_IMAGE_BASE64,
                "add a river",
                sample_context
            )

            assert result['status'] == 'success'
            assert 'image' in result
            assert result['provider'] == 'google_gemini'

    def test_handles_api_error(self, gemini_config, sample_context):
        """Test error handling when Gemini API fails."""
        with patch('models.handlers.genai.Client') as mock_client_class, \
             patch('models.handlers.types') as mock_types:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            # Mock types.Part methods
            mock_types.Part.from_bytes.return_value = Mock()
            mock_types.Part.from_text.return_value = Mock()
            mock_types.GenerateContentConfig.return_value = Mock()

            mock_client.models.generate_content.side_effect = Exception("Gemini Error")

            result = iterate_gemini(
                gemini_config,
                SAMPLE_IMAGE_BASE64,
                "add a river",
                sample_context
            )

            assert result['status'] == 'error'
            assert 'error' in result
            assert result['provider'] == 'google_gemini'

    def test_handles_empty_candidates(self, gemini_config, sample_context):
        """Test error handling when Gemini returns empty candidates."""
        with patch('models.handlers.genai.Client') as mock_client_class, \
             patch('models.handlers.types') as mock_types:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            # Mock types.Part methods
            mock_types.Part.from_bytes.return_value = Mock()
            mock_types.Part.from_text.return_value = Mock()
            mock_types.GenerateContentConfig.return_value = Mock()

            mock_response = Mock()
            mock_response.candidates = []
            mock_client.models.generate_content.return_value = mock_response

            result = iterate_gemini(
                gemini_config,
                SAMPLE_IMAGE_BASE64,
                "add a river",
                sample_context
            )

            assert result['status'] == 'error'
            assert 'empty' in result['error'].lower() or 'candidates' in result['error'].lower()

    def test_handles_no_image_in_response(self, gemini_config, sample_context):
        """Test error handling when Gemini returns no image data."""
        with patch('models.handlers.genai.Client') as mock_client_class, \
             patch('models.handlers.types') as mock_types:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            # Mock types.Part methods
            mock_types.Part.from_bytes.return_value = Mock()
            mock_types.Part.from_text.return_value = Mock()
            mock_types.GenerateContentConfig.return_value = Mock()

            # Response with candidate but no image data
            mock_part = Mock()
            mock_part.inline_data = None

            mock_candidate = Mock()
            mock_candidate.content.parts = [mock_part]

            mock_response = Mock()
            mock_response.candidates = [mock_candidate]
            mock_client.models.generate_content.return_value = mock_response

            result = iterate_gemini(
                gemini_config,
                SAMPLE_IMAGE_BASE64,
                "add a river",
                sample_context
            )

            assert result['status'] == 'error'
            assert 'image' in result['error'].lower() or 'data' in result['error'].lower()


class TestIterateOpenAI:
    """Tests for iterate_openai handler."""

    @pytest.fixture
    def openai_config(self):
        return {
            'provider': 'openai',
            'id': 'gpt-image-1',
            'api_key': 'test-openai-key'
        }

    @pytest.fixture
    def sample_context(self):
        return [
            {'iteration': 0, 'prompt': 'a dog', 'image_key': 'test/0.png'},
        ]

    def test_successful_iteration(self, openai_config, sample_context):
        """Test successful image iteration with OpenAI."""
        with patch('models.handlers.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            # Setup mock response with b64_json
            mock_response = Mock()
            mock_response.data = [Mock(b64_json=SAMPLE_IMAGE_BASE64, url=None)]
            mock_client.images.edit.return_value = mock_response

            result = iterate_openai(
                openai_config,
                SAMPLE_IMAGE_BASE64,
                "make the dog wear a hat",
                sample_context
            )

            assert result['status'] == 'success'
            assert 'image' in result
            assert result['provider'] == 'openai'

    @responses.activate
    def test_successful_iteration_with_url(self, openai_config, sample_context):
        """Test iteration when OpenAI returns URL instead of b64_json."""
        # Mock image download
        responses.add(
            responses.GET,
            "https://example.com/openai-result.png",
            body=SAMPLE_IMAGE_CONTENT,
            status=200
        )

        with patch('models.handlers.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            # Setup mock response with URL (no b64_json)
            mock_data = Mock()
            mock_data.b64_json = None
            mock_data.url = "https://example.com/openai-result.png"
            mock_response = Mock()
            mock_response.data = [mock_data]
            mock_client.images.edit.return_value = mock_response

            result = iterate_openai(
                openai_config,
                SAMPLE_IMAGE_BASE64,
                "make the dog wear a hat",
                sample_context
            )

            assert result['status'] == 'success'
            assert 'image' in result

    def test_handles_api_error(self, openai_config, sample_context):
        """Test error handling when OpenAI API fails."""
        with patch('models.handlers.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client
            mock_client.images.edit.side_effect = Exception("OpenAI API Error")

            result = iterate_openai(
                openai_config,
                SAMPLE_IMAGE_BASE64,
                "make the dog wear a hat",
                sample_context
            )

            assert result['status'] == 'error'
            assert 'error' in result
            assert result['provider'] == 'openai'

    def test_handles_empty_response(self, openai_config, sample_context):
        """Test error handling when OpenAI returns empty data."""
        with patch('models.handlers.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            mock_response = Mock()
            mock_response.data = []
            mock_client.images.edit.return_value = mock_response

            result = iterate_openai(
                openai_config,
                SAMPLE_IMAGE_BASE64,
                "make the dog wear a hat",
                sample_context
            )

            assert result['status'] == 'error'
            assert 'empty' in result['error'].lower()

    def test_accepts_base64_string_and_bytes(self, openai_config, sample_context):
        """Test handler accepts both base64 string and bytes for source_image."""
        with patch('models.handlers.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            mock_response = Mock()
            mock_response.data = [Mock(b64_json=SAMPLE_IMAGE_BASE64, url=None)]
            mock_client.images.edit.return_value = mock_response

            # Test with base64 string
            result1 = iterate_openai(
                openai_config,
                SAMPLE_IMAGE_BASE64,  # string
                "test prompt",
                sample_context
            )
            assert result1['status'] == 'success'

            # Test with bytes
            result2 = iterate_openai(
                openai_config,
                SAMPLE_IMAGE_CONTENT,  # bytes
                "test prompt",
                sample_context
            )
            assert result2['status'] == 'success'


class TestIterateHandlerIntegration:
    """Integration tests for iteration handler pipeline."""

    def test_all_handlers_return_consistent_format(self):
        """Test that all iteration handlers return consistent response format."""
        handlers = [
            ('bfl', iterate_flux),
            ('recraft', iterate_recraft),
            ('google_gemini', iterate_gemini),
            ('openai', iterate_openai),
        ]

        for provider, handler in handlers:
            config = {'provider': provider, 'id': 'test', 'api_key': 'test'}
            context = []

            # Each handler should gracefully handle errors
            result = handler(config, SAMPLE_IMAGE_BASE64, "test prompt", context)

            # All results should have these fields
            assert 'status' in result, f"{provider} handler missing 'status'"
            assert result['status'] in ['success', 'error'], f"{provider} has invalid status"
            assert 'provider' in result, f"{provider} handler missing 'provider'"

            if result['status'] == 'success':
                assert 'image' in result, f"{provider} success missing 'image'"
            else:
                assert 'error' in result, f"{provider} error missing 'error' message"
