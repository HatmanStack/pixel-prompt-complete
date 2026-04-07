"""Unit tests for the Nova Canvas (Bedrock) provider module."""

import io
import json
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from models.providers.nova import handle_nova, iterate_nova, outpaint_nova
from .fixtures.api_responses import SAMPLE_IMAGE_BASE64


@pytest.fixture
def nova_config():
    return {"provider": "bedrock_nova", "id": "amazon.nova-canvas-v1:0", "api_key": ""}


def _mock_invoke_response(payload: dict):
    body = io.BytesIO(json.dumps(payload).encode("utf-8"))
    return {"body": body}


def test_handle_nova_success(nova_config):
    with patch("models.providers.nova.get_bedrock_client") as mock_client_factory:
        client = Mock()
        mock_client_factory.return_value = client
        client.invoke_model.return_value = _mock_invoke_response(
            {"images": [SAMPLE_IMAGE_BASE64]}
        )

        result = handle_nova(nova_config, "a sunset", {})
        assert result["status"] == "success"
        assert result["provider"] == "bedrock_nova"
        # Verify TEXT_IMAGE task type was used
        call_kwargs = client.invoke_model.call_args[1]
        body = json.loads(call_kwargs["body"])
        assert body["taskType"] == "TEXT_IMAGE"


def test_handle_nova_empty_images(nova_config):
    with patch("models.providers.nova.get_bedrock_client") as mock_client_factory:
        client = Mock()
        mock_client_factory.return_value = client
        client.invoke_model.return_value = _mock_invoke_response({"images": []})

        result = handle_nova(nova_config, "x", {})
        assert result["status"] == "error"


def test_handle_nova_bedrock_error(nova_config):
    with patch("models.providers.nova.get_bedrock_client") as mock_client_factory:
        client = Mock()
        mock_client_factory.return_value = client
        client.invoke_model.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
            "InvokeModel",
        )

        result = handle_nova(nova_config, "x", {})
        assert result["status"] == "error"


def test_iterate_nova_uses_image_variation(nova_config):
    with patch("models.providers.nova.get_bedrock_client") as mock_client_factory:
        client = Mock()
        mock_client_factory.return_value = client
        client.invoke_model.return_value = _mock_invoke_response(
            {"images": [SAMPLE_IMAGE_BASE64]}
        )

        result = iterate_nova(nova_config, SAMPLE_IMAGE_BASE64, "edit", [])
        assert result["status"] == "success"
        body = json.loads(client.invoke_model.call_args[1]["body"])
        assert body["taskType"] == "IMAGE_VARIATION"
        assert body["imageVariationParams"]["images"] == [SAMPLE_IMAGE_BASE64]


def test_outpaint_nova_uses_outpainting(nova_config):
    from io import BytesIO

    from PIL import Image

    img = Image.new("RGB", (1024, 1024), (255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    real_png_bytes = buf.getvalue()

    with patch("models.providers.nova.get_bedrock_client") as mock_client_factory:
        client = Mock()
        mock_client_factory.return_value = client
        client.invoke_model.return_value = _mock_invoke_response(
            {"images": [SAMPLE_IMAGE_BASE64]}
        )

        result = outpaint_nova(nova_config, real_png_bytes, "16:9", "extend")
        assert result["status"] == "success"
        body = json.loads(client.invoke_model.call_args[1]["body"])
        assert body["taskType"] == "OUTPAINTING"
