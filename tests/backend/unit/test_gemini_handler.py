"""Unit tests for the Gemini provider module."""

from unittest.mock import Mock, patch

import pytest

from models.providers.gemini import (
    handle_google_gemini,
    iterate_gemini,
    outpaint_gemini,
)
from .fixtures.api_responses import SAMPLE_IMAGE_BASE64, SAMPLE_IMAGE_CONTENT


@pytest.fixture
def gemini_config():
    return {
        "provider": "google_gemini",
        "id": "gemini-3.1-flash-image-preview",
        "api_key": "test-key",
    }


def _make_mock_response(image_bytes=SAMPLE_IMAGE_CONTENT, empty=False, no_image=False):
    if empty:
        response = Mock()
        response.candidates = []
        return response
    part = Mock()
    if no_image:
        part.inline_data = None
    else:
        part.inline_data = Mock()
        part.inline_data.data = image_bytes
    candidate = Mock()
    candidate.content.parts = [part]
    response = Mock()
    response.candidates = [candidate]
    return response


def test_handle_google_gemini_success(gemini_config):
    with patch("models.providers.gemini._get_genai_client") as mock_client_factory:
        client = Mock()
        mock_client_factory.return_value = client
        client.models.generate_content.return_value = _make_mock_response()

        result = handle_google_gemini(gemini_config, "a sunset", {})
        assert result["status"] == "success"
        assert result["provider"] == "google_gemini"
        assert "image" in result


def test_handle_google_gemini_empty_candidates(gemini_config):
    with patch("models.providers.gemini._get_genai_client") as mock_client_factory:
        client = Mock()
        mock_client_factory.return_value = client
        client.models.generate_content.return_value = _make_mock_response(empty=True)

        result = handle_google_gemini(gemini_config, "x", {})
        assert result["status"] == "error"


def test_iterate_gemini_success(gemini_config):
    with (
        patch("models.providers.gemini._get_genai_client") as mock_client_factory,
        patch("models.providers.gemini.types") as mock_types,
    ):
        client = Mock()
        mock_client_factory.return_value = client
        mock_types.Part.from_bytes.return_value = Mock()
        mock_types.Part.from_text.return_value = Mock()
        mock_types.GenerateContentConfig.return_value = Mock()
        client.models.generate_content.return_value = _make_mock_response()

        result = iterate_gemini(
            gemini_config,
            SAMPLE_IMAGE_BASE64,
            "make sky purple",
            [{"prompt": "original"}],
        )
        assert result["status"] == "success"


def test_outpaint_gemini_success(gemini_config):
    with (
        patch("models.providers.gemini._get_genai_client") as mock_client_factory,
        patch("models.providers.gemini.types") as mock_types,
    ):
        client = Mock()
        mock_client_factory.return_value = client
        mock_types.Part.from_bytes.return_value = Mock()
        mock_types.Part.from_text.return_value = Mock()
        mock_types.GenerateContentConfig.return_value = Mock()
        client.models.generate_content.return_value = _make_mock_response()

        result = outpaint_gemini(gemini_config, SAMPLE_IMAGE_BASE64, "16:9", "extend scene")
        assert result["status"] == "success"
