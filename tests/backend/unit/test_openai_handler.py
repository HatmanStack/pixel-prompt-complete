"""Unit tests for the OpenAI provider module (DALL-E 3 + gpt-image-1 edits)."""

from unittest.mock import Mock, patch

import pytest
import requests
import responses

from models.providers.openai_provider import (
    _EDIT_MODEL,
    handle_openai,
    iterate_openai,
    outpaint_openai,
)
from .fixtures.api_responses import SAMPLE_IMAGE_BASE64, SAMPLE_IMAGE_CONTENT


@pytest.fixture
def openai_config():
    return {"provider": "openai", "id": "dall-e-3", "api_key": "test-key"}


@responses.activate
def test_handle_openai_dalle3_success(openai_config):
    responses.add(
        responses.GET,
        "https://example.com/img.png",
        body=SAMPLE_IMAGE_CONTENT,
        status=200,
    )
    with patch("models.providers.openai_provider._get_openai_client") as mock_factory:
        client = Mock()
        mock_factory.return_value = client
        mock_response = Mock()
        mock_response.data = [Mock(url="https://example.com/img.png")]
        client.images.generate.return_value = mock_response

        result = handle_openai(openai_config, "a cat", {})
        assert result["status"] == "success"
        assert result["model"] == "dall-e-3"
        kwargs = client.images.generate.call_args[1]
        assert kwargs["model"] == "dall-e-3"


def test_handle_openai_dalle3_empty_response(openai_config):
    with patch("models.providers.openai_provider._get_openai_client") as mock_factory:
        client = Mock()
        mock_factory.return_value = client
        mock_response = Mock()
        mock_response.data = []
        client.images.generate.return_value = mock_response

        result = handle_openai(openai_config, "x", {})
        assert result["status"] == "error"


def test_handle_openai_timeout(openai_config):
    with patch("models.providers.openai_provider._get_openai_client") as mock_factory:
        client = Mock()
        mock_factory.return_value = client
        client.images.generate.side_effect = requests.Timeout("oops")

        result = handle_openai(openai_config, "x", {})
        assert result["status"] == "error"


def test_iterate_openai_uses_gpt_image_1(openai_config):
    """Critical ADR-5 test: iterate must use gpt-image-1 even when config says dall-e-3."""
    with patch("models.providers.openai_provider._get_openai_client") as mock_factory:
        client = Mock()
        mock_factory.return_value = client
        mock_response = Mock()
        mock_response.data = [Mock(b64_json=SAMPLE_IMAGE_BASE64, url=None)]
        client.images.edit.return_value = mock_response

        result = iterate_openai(openai_config, SAMPLE_IMAGE_BASE64, "edit", [])
        assert result["status"] == "success"
        kwargs = client.images.edit.call_args[1]
        assert kwargs["model"] == "gpt-image-1"
        assert kwargs["model"] == _EDIT_MODEL


def test_outpaint_openai_uses_gpt_image_1(openai_config):
    """Critical ADR-5 test: outpaint must use gpt-image-1 even when config says dall-e-3."""
    from PIL import Image
    from io import BytesIO

    img = Image.new("RGB", (1024, 1024), (255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    real_png_bytes = buf.getvalue()

    with patch("models.providers.openai_provider._get_openai_client") as mock_factory:
        client = Mock()
        mock_factory.return_value = client
        mock_response = Mock()
        mock_response.data = [Mock(b64_json=SAMPLE_IMAGE_BASE64, url=None)]
        client.images.edit.return_value = mock_response

        result = outpaint_openai(openai_config, real_png_bytes, "16:9", "extend")
        assert result["status"] == "success"
        kwargs = client.images.edit.call_args[1]
        assert kwargs["model"] == "gpt-image-1"


# --- Download error handling tests ---


def test_handle_openai_connection_error(openai_config):
    """ConnectionError during image download produces a specific error message."""
    with patch("models.providers.openai_provider._get_openai_client") as mock_factory:
        client = Mock()
        mock_factory.return_value = client
        mock_response = Mock()
        mock_response.data = [Mock(url="https://example.com/img.png")]
        client.images.generate.return_value = mock_response

        with patch("models.providers.openai_provider.requests.get") as mock_get:
            mock_get.side_effect = requests.ConnectionError("Connection refused")
            result = handle_openai(openai_config, "a cat", {})
            assert result["status"] == "error"
            assert "connection failed" in result["error"].lower()


def test_handle_openai_http_error(openai_config):
    """HTTPError during image download includes status code in error message."""
    with patch("models.providers.openai_provider._get_openai_client") as mock_factory:
        client = Mock()
        mock_factory.return_value = client
        mock_response = Mock()
        mock_response.data = [Mock(url="https://example.com/img.png")]
        client.images.generate.return_value = mock_response

        with patch("models.providers.openai_provider.requests.get") as mock_get:
            http_err_response = Mock()
            http_err_response.status_code = 403
            mock_get.side_effect = requests.HTTPError(
                "403 Forbidden", response=http_err_response
            )
            result = handle_openai(openai_config, "a cat", {})
            assert result["status"] == "error"
            assert "403" in result["error"]
