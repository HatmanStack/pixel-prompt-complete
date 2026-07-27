"""
Image Storage utilities for Pixel Prompt Complete.

Handles saving generated images to S3 with metadata and gallery management.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from botocore.exceptions import ClientError

from .logger import StructuredLogger
from .retry import retry_with_backoff

PUBLIC_PREFIX = "sessions"

# Objects under this prefix are deliberately NOT covered by the CloudFront
# origin access policy, so they have no unsigned URL. Reaching them requires
# a presigned URL, which the Lambda only issues after checking ownership.
PRIVATE_PREFIX = "private"

# Every S3 key prefix this module writes an object under.
# tests/backend/unit/test_iam_prefix_coverage.py reads this set and asserts the
# Lambda execution role in backend/template.yaml grants exactly these prefixes.
# Adding a prefix without adding it here leaves the check unable to see it;
# adding it here without granting it in the template fails that test. No
# runtime test can catch the gap, because neither moto nor MiniStack enforces
# IAM -- which is how private/* shipped ungranted.
WRITTEN_PREFIXES: frozenset[str] = frozenset({PUBLIC_PREFIX, PRIVATE_PREFIX})


class ImageStorage:
    """
    Manages image storage in S3 with metadata.
    """

    def __init__(self, s3_client, bucket_name: str, cloudfront_domain: str):
        """
        Initialize Image Storage.

        Args:
            s3_client: boto3 S3 client
            bucket_name: S3 bucket name
            cloudfront_domain: CloudFront distribution domain
        """
        self.s3 = s3_client
        self.bucket = bucket_name
        self.cloudfront_domain = cloudfront_domain

    def _store_image(self, base64_image: str, key: str) -> None:
        """Decode base64 image and store raw bytes in S3."""
        raw_bytes = base64.b64decode(base64_image)
        self._put_object_with_retry(
            key=key,
            body=raw_bytes,
            content_type="image/png",
        )

    @retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=4.0)
    def _put_object_with_retry(self, key: str, body: str | bytes, content_type: str):
        """
        Upload object to S3 with retry logic.

        Args:
            key: S3 key
            body: Object content (string or bytes)
            content_type: Content type

        Raises:
            Exception: If upload fails after retries
        """
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)

    def upload_image(
        self,
        base64_image: str,
        target: str,
        model_name: str,
        iteration: Optional[int] = None,
        session_id: Optional[str] = None,
        visibility: str = "public",
    ) -> str:
        """Upload a generated image to S3 as raw PNG bytes.

        The key encodes visibility structurally rather than recording it as
        metadata to be checked later. A private image has no unsigned URL
        because its prefix is outside the bucket policy, so forgetting a check
        on some future read path cannot expose it.

        ``session_id`` also disambiguates the folder. It used to be a bare
        second-granularity timestamp shared by every session that started in
        the same second, which merged unrelated users into one gallery folder
        and, when the same model finished in the same second, produced an
        identical key and silently overwrote the earlier image.
        """
        normalized_model = self._normalize_model_name(model_name)
        iter_suffix = f"-iter{iteration}" if iteration is not None else ""

        if visibility == "private":
            if not session_id:
                raise ValueError("session_id is required for private uploads")
            key = f"{PRIVATE_PREFIX}/{session_id}/{normalized_model}{iter_suffix}.png"
        else:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            folder = f"{target}-{session_id[:8]}" if session_id else target
            key = f"{PUBLIC_PREFIX}/{folder}/{normalized_model}-{timestamp}{iter_suffix}.png"

        self._store_image(base64_image, key)

        return key

    def is_private_key(self, image_key: str) -> bool:
        """Return True if ``image_key`` has no unsigned URL."""
        return image_key.startswith(f"{PRIVATE_PREFIX}/")

    def get_image(self, image_key: str) -> Optional[Dict]:
        """
        Get image data from S3.

        For old JSON-format keys (.json): parses JSON and returns the metadata dict.
        For new raw-format keys (.png): reads raw bytes, base64-encodes them,
        and returns a dict with 'output' set to the base64 string.

        Args:
            image_key: S3 key of the image

        Returns:
            Image metadata dict (with 'output' field) or None if not found
        """
        try:
            response = self._get_object_with_retry(image_key)
            raw = response["Body"].read()

            if image_key.endswith(".json"):
                return json.loads(raw.decode("utf-8"))

            # New raw PNG format: wrap in a dict matching the old interface
            return {"output": base64.b64encode(raw).decode("utf-8")}

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            else:
                raise

    def get_image_bytes(self, image_key: str) -> bytes | None:
        """
        Read raw bytes from S3 for the given key.

        Args:
            image_key: S3 key of the image

        Returns:
            Raw bytes or None if not found
        """
        try:
            response = self._get_object_with_retry(image_key)
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    @retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=4.0)
    def _get_object_with_retry(self, key: str):
        """
        Get object from S3 with retry logic.

        Args:
            key: S3 key

        Returns:
            S3 get_object response

        Raises:
            Exception: If get fails after retries
        """
        return self.s3.get_object(Bucket=self.bucket, Key=key)

    # Gallery folder pattern: YYYY-MM-DD-HH-MM-SS, optionally suffixed with the
    # first 8 characters of the session id. The suffix is what keeps two
    # sessions that started in the same second from sharing a folder; the
    # optional group keeps folders written before that change listable.
    #
    # The suffix class is alphanumeric rather than hex even though session ids
    # are UUIDs today. Anchored as it is, this still cannot match a session
    # state folder (a full UUID is 36 characters), and the failure mode of
    # being too strict is that galleries silently stop appearing.
    _GALLERY_FOLDER_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}(?:-[0-9a-zA-Z]{8})?$")

    def validate_gallery_id(self, gallery_id: str) -> bool:
        """Return True if ``gallery_id`` matches the gallery timestamp format."""
        return bool(self._GALLERY_FOLDER_RE.match(gallery_id))

    def get_image_metadata(self, image_key: str) -> Optional[Dict]:
        """Return image metadata excluding the base64 ``output`` blob.

        For .json keys: reads JSON and strips the ``output`` field.
        For .png keys: returns None (metadata lives in status.json, not the image file).
        """
        if not image_key.endswith(".json"):
            return None
        data = self.get_image(image_key)
        if data is None:
            return None
        data.pop("output", None)
        return data

    def list_galleries(self) -> List[str]:
        """
        List all gallery folders (target timestamps) from the sessions prefix.

        Filters out non-gallery folders (e.g. session UUID folders) by matching
        the timestamp pattern YYYY-MM-DD-HH-MM-SS.

        Returns:
            List of gallery folder names (target timestamps)

        Raises:
            ClientError: If the S3 operation fails (e.g., IAM, throttling)
        """
        try:
            galleries = []
            kwargs = {
                "Bucket": self.bucket,
                "Prefix": "sessions/",
                "Delimiter": "/",
            }

            while True:
                response = self.s3.list_objects_v2(**kwargs)

                # Extract folder names from CommonPrefixes
                if "CommonPrefixes" in response:
                    for prefix in response["CommonPrefixes"]:
                        # e.g., "sessions/2025-11-15-14-30-45/" -> "2025-11-15-14-30-45"
                        folder = prefix["Prefix"].split("/")[-2]
                        if self._GALLERY_FOLDER_RE.match(folder):
                            galleries.append(folder)

                # Continue paginating if there are more results
                if response.get("IsTruncated"):
                    kwargs["ContinuationToken"] = response["NextContinuationToken"]
                else:
                    break

            # Sort by timestamp (newest first)
            galleries.sort(reverse=True)

            return galleries

        except ClientError as e:
            StructuredLogger.error(f"Failed to list galleries from S3: {e}")
            raise

    def list_gallery_images(self, gallery_folder: str) -> List[str]:
        """
        List all image keys in a gallery folder.

        Args:
            gallery_folder: Gallery folder name (target timestamp)

        Returns:
            List of S3 keys for images in the gallery

        Raises:
            ClientError: If the S3 operation fails (e.g., IAM, throttling)
        """
        try:
            prefix = f"sessions/{gallery_folder}/"
            images = []
            kwargs = {
                "Bucket": self.bucket,
                "Prefix": prefix,
            }

            while True:
                response = self.s3.list_objects_v2(**kwargs)

                if "Contents" in response:
                    for obj in response["Contents"]:
                        key = obj["Key"]
                        # Include image files (.json legacy and .png new format)
                        if key.endswith((".json", ".png")):
                            images.append(key)

                # Continue paginating if there are more results
                if response.get("IsTruncated"):
                    kwargs["ContinuationToken"] = response["NextContinuationToken"]
                else:
                    break

            return images

        except ClientError as e:
            StructuredLogger.error(f"Failed to list gallery images from S3: {e}")
            raise

    def generate_presigned_download_url(
        self, image_key: str, filename: str, expires_in: int = 300
    ) -> str:
        """Generate a presigned S3 URL for downloading an image.

        Args:
            image_key: S3 key of the image
            filename: Suggested download filename
            expires_in: URL expiry in seconds (default 300 = 5 minutes)

        Returns:
            Presigned URL string
        """
        return self.s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": image_key,
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
                "ResponseContentType": "image/png",
            },
            ExpiresIn=expires_in,
        )

    def generate_presigned_view_url(self, image_key: str, expires_in: int = 3600) -> str:
        """Generate a presigned S3 URL for viewing a private image inline.

        Distinct from ``generate_presigned_download_url``, which forces an
        attachment disposition. This one renders in an <img> tag.
        """
        return self.s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": image_key,
                "ResponseContentType": "image/png",
            },
            ExpiresIn=expires_in,
        )

    def get_cloudfront_url(self, s3_key: str) -> str:
        """
        Get CloudFront URL for an S3 key.

        Args:
            s3_key: S3 key of the object

        Returns:
            CloudFront URL
        """
        return f"https://{self.cloudfront_domain}/{s3_key}"

    def _normalize_model_name(self, model_name: str) -> str:
        """
        Normalize model name for use in filenames.

        Args:
            model_name: Original model name

        Returns:
            Normalized model name (lowercase, alphanumeric + hyphens)
        """
        # Convert to lowercase
        normalized = model_name.lower()

        # Replace spaces with hyphens
        normalized = normalized.replace(" ", "-")

        # Remove special characters (keep alphanumeric and hyphens)
        normalized = re.sub(r"[^a-z0-9\-]", "", normalized)

        # Remove consecutive hyphens
        normalized = re.sub(r"-+", "-", normalized)

        # Remove leading/trailing hyphens
        normalized = normalized.strip("-")

        return normalized
