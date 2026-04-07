"""Unit tests for the Adobe Firefly provider module."""

from unittest.mock import Mock, patch

import pytest

from models.providers.firefly import (
    _get_firefly_access_token,
    handle_firefly,
    iterate_firefly,
    outpaint_firefly,
)
from .fixtures.api_responses import SAMPLE_IMAGE_BASE64, SAMPLE_IMAGE_CONTENT


@pytest.fixture
def firefly_config():
    return {
        "provider": "adobe_firefly",
        "id": "firefly-image-5",
        "api_key": "",
        "client_id": "test-client-id",
        "client_secret": "test-secret",
    }


def _mock_token_response():
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"access_token": "test-token"}
    response.raise_for_status = Mock()
    return response


def _mock_generate_response():
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "outputs": [{"image": {"url": "https://example.com/firefly.png"}}]
    }
    response.raise_for_status = Mock()
    return response


def _mock_storage_response():
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"images": [{"id": "upload-123"}]}
    response.raise_for_status = Mock()
    return response


def test_get_firefly_access_token_success():
    with patch("models.providers.firefly.requests.post") as mock_post:
        mock_post.return_value = _mock_token_response()
        token = _get_firefly_access_token("cid", "csecret")
        assert token == "test-token"


def test_get_firefly_access_token_missing_credentials():
    with pytest.raises(ValueError):
        _get_firefly_access_token("", "")


def test_get_firefly_access_token_no_token_in_response():
    with patch("models.providers.firefly.requests.post") as mock_post:
        resp = Mock()
        resp.json.return_value = {}
        resp.raise_for_status = Mock()
        mock_post.return_value = resp
        with pytest.raises(ValueError):
            _get_firefly_access_token("cid", "csecret")


def test_handle_firefly_success(firefly_config):
    with (
        patch("models.providers.firefly.requests.post") as mock_post,
        patch("models.providers.firefly._download_image_as_base64") as mock_download,
    ):
        mock_post.side_effect = [_mock_token_response(), _mock_generate_response()]
        mock_download.return_value = SAMPLE_IMAGE_BASE64

        result = handle_firefly(firefly_config, "a sunset", {})
        assert result["status"] == "success"
        assert result["provider"] == "adobe_firefly"


def test_handle_firefly_token_failure(firefly_config):
    with patch("models.providers.firefly.requests.post") as mock_post:
        mock_post.side_effect = Exception("token failure")
        result = handle_firefly(firefly_config, "a sunset", {})
        assert result["status"] == "error"


def test_iterate_firefly_success(firefly_config):
    with (
        patch("models.providers.firefly.requests.post") as mock_post,
        patch("models.providers.firefly._download_image_as_base64") as mock_download,
    ):
        mock_post.side_effect = [
            _mock_token_response(),
            _mock_storage_response(),
            _mock_generate_response(),
        ]
        mock_download.return_value = SAMPLE_IMAGE_BASE64

        result = iterate_firefly(firefly_config, SAMPLE_IMAGE_BASE64, "edit", [])
        assert result["status"] == "success"


def test_outpaint_firefly_success(firefly_config):
    from io import BytesIO

    from PIL import Image

    img = Image.new("RGB", (1024, 1024), (255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    real_png = buf.getvalue()

    with (
        patch("models.providers.firefly.requests.post") as mock_post,
        patch("models.providers.firefly._download_image_as_base64") as mock_download,
    ):
        mock_post.side_effect = [
            _mock_token_response(),
            _mock_storage_response(),
            _mock_generate_response(),
        ]
        mock_download.return_value = SAMPLE_IMAGE_BASE64

        result = outpaint_firefly(firefly_config, real_png, "16:9", "extend")
        assert result["status"] == "success"
