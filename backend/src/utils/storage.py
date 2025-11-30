"""
Image Storage utilities for Pixel Prompt Complete.

Handles saving generated images to S3 with metadata and gallery management.
"""

import json
import re
import base64
import io
from datetime import datetime, timezone
from typing import Dict, List, Optional
from botocore.exceptions import ClientError
from PIL import Image

from .retry import retry_with_backoff


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

    def save_image(
        self,
        base64_image: str,
        model_name: str,
        prompt: str,
        target: str
    ) -> str:
        """
        Save generated image to S3 with metadata and thumbnail.

        Args:
            base64_image: Base64-encoded image data
            model_name: Name of the AI model
            prompt: Text prompt used
            target: Target timestamp (groups images together)

        Returns:
            S3 key where image is stored
        """
        # Normalize model name for filename
        normalized_model = self._normalize_model_name(model_name)

        # Generate timestamp
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')

        # Build S3 key
        key = f"group-images/{target}/{normalized_model}-{timestamp}.json"

        # Build metadata JSON
        metadata = {
            'output': base64_image,
            'model': model_name,
            'prompt': prompt,
            'target': target,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'NSFW': False  # Will be updated by content filter if needed
        }

        # Upload to S3 with retry logic
        self._put_object_with_retry(
            key=key,
            body=json.dumps(metadata),
            content_type='application/json'
        )


        # Generate and save thumbnail
        try:
            thumbnail_base64 = self._generate_thumbnail(base64_image)
            thumbnail_key = f"group-images/{target}/{normalized_model}-{timestamp}-thumb.json"

            thumbnail_metadata = {
                'output': thumbnail_base64,
                'model': model_name,
                'prompt': prompt,
                'target': target,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'NSFW': False,
                'thumbnail': True
            }

            self._put_object_with_retry(
                key=thumbnail_key,
                body=json.dumps(thumbnail_metadata),
                content_type='application/json'
            )

        except Exception:
            # Continue even if thumbnail fails - not critical
            pass

        return key

    @retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=4.0)
    def _put_object_with_retry(self, key: str, body: str, content_type: str):
        """
        Upload object to S3 with retry logic.

        Args:
            key: S3 key
            body: Object content
            content_type: Content type

        Raises:
            Exception: If upload fails after retries
        """
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type
        )

    def get_image(self, image_key: str) -> Optional[Dict]:
        """
        Get image data from S3.

        Args:
            image_key: S3 key of the image

        Returns:
            Image metadata dict or None if not found
        """
        try:
            response = self._get_object_with_retry(image_key)
            metadata = json.loads(response['Body'].read().decode('utf-8'))
            return metadata

        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            else:
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

    def list_galleries(self) -> List[str]:
        """
        List all gallery folders (target timestamps).

        Returns:
            List of gallery folder names (target timestamps)
        """
        try:
            # List objects with prefix and delimiter to get folders
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix='group-images/',
                Delimiter='/'
            )

            # Extract folder names from CommonPrefixes
            galleries = []
            if 'CommonPrefixes' in response:
                for prefix in response['CommonPrefixes']:
                    # Extract folder name from prefix
                    # e.g., "group-images/2025-11-15-14-30-45/" -> "2025-11-15-14-30-45"
                    folder = prefix['Prefix'].split('/')[-2]
                    galleries.append(folder)

            # Sort by timestamp (newest first)
            galleries.sort(reverse=True)


            return galleries

        except Exception:
            return []

    def list_gallery_images(self, gallery_folder: str) -> List[str]:
        """
        List all image keys in a gallery folder.

        Args:
            gallery_folder: Gallery folder name (target timestamp)

        Returns:
            List of S3 keys for images in the gallery
        """
        try:
            prefix = f"group-images/{gallery_folder}/"

            # List all objects in the folder
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix
            )

            images = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    key = obj['Key']
                    # Only include .json files (not folders)
                    if key.endswith('.json'):
                        images.append(key)


            return images

        except Exception:
            return []

    def get_cloudfront_url(self, s3_key: str) -> str:
        """
        Get CloudFront URL for an S3 key.

        Args:
            s3_key: S3 key of the object

        Returns:
            CloudFront URL
        """
        return f"https://{self.cloudfront_domain}/{s3_key}"

    def _generate_thumbnail(self, base64_image: str, size: int = 200, quality: int = 75) -> str:
        """
        Generate a thumbnail from base64 image data.

        Args:
            base64_image: Base64-encoded image data
            size: Maximum dimension for thumbnail (default 200px)
            quality: JPEG quality for compression (default 75)

        Returns:
            Base64-encoded thumbnail image

        Raises:
            Exception: If thumbnail generation fails
        """
        # Decode base64 to bytes
        image_bytes = base64.b64decode(base64_image)

        # Open image with Pillow
        img = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if necessary (for PNG with transparency)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background

        # Calculate thumbnail size maintaining aspect ratio
        img.thumbnail((size, size), Image.Resampling.LANCZOS)

        # Save to bytes buffer as JPEG with compression
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
        buffer.seek(0)

        # Encode to base64
        thumbnail_base64 = base64.b64encode(buffer.read()).decode('utf-8')


        return thumbnail_base64

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
        normalized = normalized.replace(' ', '-')

        # Remove special characters (keep alphanumeric and hyphens)
        normalized = re.sub(r'[^a-z0-9\-]', '', normalized)

        # Remove consecutive hyphens
        normalized = re.sub(r'-+', '-', normalized)

        # Remove leading/trailing hyphens
        normalized = normalized.strip('-')

        return normalized
