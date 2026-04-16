"""
Tests for the storage refactor: raw PNG images in S3 instead of base64 JSON.
"""

import base64
import json
from unittest.mock import patch

import pytest

from utils.storage import ImageStorage

from .fixtures.api_responses import SAMPLE_IMAGE_BASE64


class TestUploadImageRawPng:
    """Task 1.1: upload_image stores raw PNG bytes."""

    def test_upload_image_stores_raw_png(self, mock_s3):
        """upload_image() should store decoded PNG bytes, not JSON."""
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, "cdn.example.com")

        key = storage.upload_image(
            base64_image=SAMPLE_IMAGE_BASE64,
            target="2025-11-16-10-30-00",
            model_name="gemini",
            prompt="test prompt",
            iteration=0,
        )

        # Key should end in .png
        assert key.endswith(".png"), f"Expected .png key, got {key}"

        # S3 object should be raw bytes, not JSON
        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()
        expected_bytes = base64.b64decode(SAMPLE_IMAGE_BASE64)
        assert body == expected_bytes

        # Content-Type should be image/png
        assert obj["ContentType"] == "image/png"

    def test_upload_image_key_format(self, mock_s3):
        """upload_image() key should have correct structure."""
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, "cdn.example.com")

        key = storage.upload_image(
            base64_image=SAMPLE_IMAGE_BASE64,
            target="2025-11-16-10-30-00",
            model_name="gemini",
            prompt="test prompt",
            iteration=2,
        )

        assert key.startswith("sessions/2025-11-16-10-30-00/")
        assert "gemini" in key
        assert "iter2" in key
        assert key.endswith(".png")

    def test_upload_image_without_iteration(self, mock_s3):
        """upload_image() without iteration should not have iter suffix."""
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, "cdn.example.com")

        key = storage.upload_image(
            base64_image=SAMPLE_IMAGE_BASE64,
            target="2025-11-16-10-30-00",
            model_name="nova",
            prompt="test",
        )

        assert key.endswith(".png")
        assert "iter" not in key


class TestGetImageBackwardCompat:
    """Task 1.1: get_image handles both old JSON and new PNG formats."""

    def test_get_image_reads_old_json_format(self, mock_s3):
        """get_image() should still parse old JSON-format image files."""
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, "cdn.example.com")

        key = "sessions/test-gallery/gemini-20250101.json"
        metadata = {
            "output": SAMPLE_IMAGE_BASE64,
            "model": "gemini",
            "prompt": "old prompt",
            "timestamp": "2025-01-01T00:00:00Z",
        }
        s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(metadata))

        result = storage.get_image(key)
        assert result is not None
        assert result["output"] == SAMPLE_IMAGE_BASE64
        assert result["model"] == "gemini"

    def test_get_image_reads_new_png_format(self, mock_s3):
        """get_image() should read raw PNG bytes and return base64 in output field."""
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, "cdn.example.com")

        raw_bytes = base64.b64decode(SAMPLE_IMAGE_BASE64)
        key = "sessions/test-gallery/gemini-20250101.png"
        s3.put_object(Bucket=bucket, Key=key, Body=raw_bytes, ContentType="image/png")

        result = storage.get_image(key)
        assert result is not None
        assert result["output"] == SAMPLE_IMAGE_BASE64


class TestGetImageBytes:
    """Task 1.1: get_image_bytes returns raw bytes."""

    def test_get_image_bytes_returns_raw(self, mock_s3):
        """get_image_bytes() should return raw bytes from S3."""
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, "cdn.example.com")

        raw_bytes = base64.b64decode(SAMPLE_IMAGE_BASE64)
        key = "sessions/test/image.png"
        s3.put_object(Bucket=bucket, Key=key, Body=raw_bytes)

        result = storage.get_image_bytes(key)
        assert result == raw_bytes

    def test_get_image_bytes_returns_none_for_missing(self, mock_s3):
        """get_image_bytes() should return None for nonexistent keys."""
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, "cdn.example.com")

        result = storage.get_image_bytes("nonexistent/key.png")
        assert result is None


class TestListGalleryImagesBothFormats:
    """Task 1.1: list_gallery_images includes both .json and .png files."""

    def test_list_gallery_images_includes_both_formats(self, mock_s3):
        """list_gallery_images() should return both .json and .png files."""
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, "cdn.example.com")

        gallery_id = "2025-11-16-10-00-00"
        s3.put_object(
            Bucket=bucket,
            Key=f"sessions/{gallery_id}/old-image.json",
            Body=json.dumps({"model": "gemini"}),
        )
        s3.put_object(
            Bucket=bucket,
            Key=f"sessions/{gallery_id}/new-image.png",
            Body=b"raw png bytes",
            ContentType="image/png",
        )

        images = storage.list_gallery_images(gallery_id)
        # Should include both .json and .png image files
        assert len(images) == 2
        extensions = {img.rsplit(".", 1)[-1] for img in images}
        assert extensions == {"json", "png"}


class TestGetImageMetadataPng:
    """Task 1.1: get_image_metadata for PNG keys returns None."""

    def test_get_image_metadata_png_returns_none(self, mock_s3):
        """get_image_metadata() should return None for .png keys."""
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, "cdn.example.com")

        raw_bytes = base64.b64decode(SAMPLE_IMAGE_BASE64)
        key = "sessions/test/image.png"
        s3.put_object(Bucket=bucket, Key=key, Body=raw_bytes)

        result = storage.get_image_metadata(key)
        assert result is None


class TestLoadSourceImageFormats:
    """Task 1.3: _load_source_image handles both old JSON and new PNG formats."""

    def _make_session(self, image_key, iteration_count=1):
        return {
            "models": {
                "gemini": {
                    "iterationCount": iteration_count,
                    "iterations": [
                        {
                            "index": 0,
                            "status": "completed",
                            "imageKey": image_key,
                        }
                    ],
                }
            }
        }

    def test_load_source_image_new_format(self, mock_s3):
        """_load_source_image should return base64 for .png image keys."""
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, "cdn.example.com")

        raw_bytes = base64.b64decode(SAMPLE_IMAGE_BASE64)
        png_key = "sessions/test-session/gemini-20250101-iter0.png"
        s3.put_object(Bucket=bucket, Key=png_key, Body=raw_bytes, ContentType="image/png")

        session = self._make_session(png_key)

        with (
            patch("lambda_function.session_manager") as mock_sm,
            patch("lambda_function.image_storage", storage),
        ):
            mock_sm.get_session.return_value = session
            from lambda_function import _load_source_image

            result, err = _load_source_image("test-session", "gemini")

        assert err is None
        assert result is not None
        source_b64, count = result
        assert source_b64 == SAMPLE_IMAGE_BASE64
        assert count == 1

    def test_load_source_image_old_format(self, mock_s3):
        """_load_source_image should return base64 for .json image keys."""
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, "cdn.example.com")

        json_key = "sessions/test-session/gemini-20250101-iter0.json"
        metadata = {
            "output": SAMPLE_IMAGE_BASE64,
            "model": "gemini",
            "prompt": "test",
        }
        s3.put_object(Bucket=bucket, Key=json_key, Body=json.dumps(metadata))

        session = self._make_session(json_key)

        with (
            patch("lambda_function.session_manager") as mock_sm,
            patch("lambda_function.image_storage", storage),
        ):
            mock_sm.get_session.return_value = session
            from lambda_function import _load_source_image

            result, err = _load_source_image("test-session", "gemini")

        assert err is None
        assert result is not None
        source_b64, count = result
        assert source_b64 == SAMPLE_IMAGE_BASE64
        assert count == 1
