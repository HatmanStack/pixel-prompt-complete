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


class TestGalleryDetailFormats:
    """Task 1.4: Gallery detail handles both old JSON and new PNG formats."""

    def test_gallery_detail_new_format(self, mock_s3):
        """Gallery detail should return CloudFront URLs for .png files with parsed model names."""
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, "cdn.example.com")

        gallery_id = "2025-11-16-10-00-00"
        s3.put_object(
            Bucket=bucket,
            Key=f"sessions/{gallery_id}/gemini-20250116100000-iter0.png",
            Body=base64.b64decode(SAMPLE_IMAGE_BASE64),
            ContentType="image/png",
        )

        with (
            patch("lambda_function.image_storage", storage),
        ):
            from lambda_function import handle_gallery_detail

            event = {"rawPath": f"/gallery/{gallery_id}"}
            resp = handle_gallery_detail(event, "test-corr-id")

        body = json.loads(resp["body"])
        assert resp["statusCode"] == 200
        assert body["total"] == 1
        img = body["images"][0]
        assert img["url"].endswith(".png")
        assert img["model"] == "gemini"

    def test_gallery_detail_mixed_formats(self, mock_s3):
        """Gallery detail should return images for both .json and .png files."""
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, "cdn.example.com")

        gallery_id = "2025-11-16-10-00-00"
        # Old format
        s3.put_object(
            Bucket=bucket,
            Key=f"sessions/{gallery_id}/openai-20250116100000.json",
            Body=json.dumps({
                "output": SAMPLE_IMAGE_BASE64,
                "model": "openai",
                "prompt": "test",
                "timestamp": "2025-01-16T10:00:00Z",
            }),
        )
        # New format
        s3.put_object(
            Bucket=bucket,
            Key=f"sessions/{gallery_id}/gemini-20250116100000-iter0.png",
            Body=base64.b64decode(SAMPLE_IMAGE_BASE64),
            ContentType="image/png",
        )

        with (
            patch("lambda_function.image_storage", storage),
        ):
            from lambda_function import handle_gallery_detail

            event = {"rawPath": f"/gallery/{gallery_id}"}
            resp = handle_gallery_detail(event, "test-corr-id")

        body = json.loads(resp["body"])
        assert resp["statusCode"] == 200
        assert body["total"] == 2
        models = {img["model"] for img in body["images"]}
        assert "openai" in models
        assert "gemini" in models


class TestGeneratePresignedDownloadUrl:
    """Task 1.5: ImageStorage.generate_presigned_download_url."""

    def test_generate_presigned_download_url(self, mock_s3):
        """generate_presigned_download_url should return a presigned URL string."""
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, "cdn.example.com")

        # Put an object so the key exists
        key = "sessions/test-session/gemini-20250101-iter0.png"
        s3.put_object(Bucket=bucket, Key=key, Body=b"image data")

        url = storage.generate_presigned_download_url(key, "gemini-iteration-0.png")
        assert isinstance(url, str)
        assert bucket in url or key in url  # URL references the object


class TestDownloadEndpoint:
    """Task 1.5: GET /download/{sessionId}/{model}/{iterationIndex}."""

    def _make_session(self, model, image_key, iteration_index=0):
        return {
            "models": {
                model: {
                    "iterationCount": 1,
                    "iterations": [
                        {
                            "index": iteration_index,
                            "status": "completed",
                            "imageKey": image_key,
                        }
                    ],
                }
            }
        }

    def _make_event(self, session_id, model, iteration_index):
        return {
            "rawPath": f"/download/{session_id}/{model}/{iteration_index}",
            "requestContext": {"http": {"method": "GET"}},
        }

    def test_download_returns_presigned_url(self, mock_s3):
        """Download endpoint should return a JSON body with url and filename."""
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, "cdn.example.com")

        image_key = "sessions/test-session/gemini-20250101-iter0.png"
        s3.put_object(Bucket=bucket, Key=image_key, Body=b"image data")
        session = self._make_session("gemini", image_key)

        with (
            patch("lambda_function.session_manager") as mock_sm,
            patch("lambda_function.image_storage", storage),
        ):
            mock_sm.get_session.return_value = session
            from lambda_function import handle_download

            resp = handle_download(self._make_event("test-session", "gemini", "0"), "corr-id")

        body = json.loads(resp["body"])
        assert resp["statusCode"] == 200
        assert "url" in body
        assert body["filename"] == "gemini-iteration-0.png"

    def test_download_missing_session_returns_404(self, mock_s3):
        """Download with nonexistent session should return 404."""
        s3, bucket = mock_s3

        with (
            patch("lambda_function.session_manager") as mock_sm,
        ):
            mock_sm.get_session.return_value = None
            from lambda_function import handle_download

            resp = handle_download(
                self._make_event("nonexistent", "gemini", "0"), "corr-id"
            )

        assert resp["statusCode"] == 404

    def test_download_missing_iteration_returns_404(self, mock_s3):
        """Download with nonexistent iteration index should return 404."""
        s3, bucket = mock_s3

        session = self._make_session("gemini", "some-key.png", iteration_index=0)

        with (
            patch("lambda_function.session_manager") as mock_sm,
        ):
            mock_sm.get_session.return_value = session
            from lambda_function import handle_download

            # Ask for iteration 5 which doesn't exist
            resp = handle_download(
                self._make_event("test-session", "gemini", "5"), "corr-id"
            )

        assert resp["statusCode"] == 404

    def test_download_invalid_session_id_returns_400(self, mock_s3):
        """Download with invalid session ID format should return 400."""
        with (
            patch("lambda_function.session_manager"),
        ):
            from lambda_function import handle_download

            resp = handle_download(
                self._make_event("../../etc/passwd", "gemini", "0"), "corr-id"
            )

        assert resp["statusCode"] == 400

    def test_download_invalid_model_returns_400(self, mock_s3):
        """Download with invalid model name should return 400."""
        with (
            patch("lambda_function.session_manager"),
        ):
            from lambda_function import handle_download

            resp = handle_download(
                self._make_event("valid-session", "invalid-model", "0"), "corr-id"
            )

        assert resp["statusCode"] == 400


class TestDownloadRouteRegistration:
    """Task 1.5: Route registration in lambda_handler."""

    def test_download_route_registered(self, mock_s3):
        """GET /download/... should be routed to handle_download."""
        with (
            patch("lambda_function.session_manager") as mock_sm,
            patch("lambda_function.handle_download") as mock_handler,
        ):
            mock_handler.return_value = {"statusCode": 200, "body": "{}"}
            from lambda_function import lambda_handler

            event = {
                "rawPath": "/download/test-session/gemini/0",
                "requestContext": {"http": {"method": "GET"}},
                "headers": {},
            }
            lambda_handler(event, None)
            mock_handler.assert_called_once()


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
