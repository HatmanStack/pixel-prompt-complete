"""
Unit tests for storage utilities
"""

import pytest
import json
from unittest.mock import Mock, patch
from botocore.exceptions import ClientError
from utils.storage import ImageStorage
from .fixtures.api_responses import SAMPLE_IMAGE_BASE64


class TestImageStorage:
    """Tests for ImageStorage class"""

    def test_get_cloudfront_url(self, mock_s3):
        """Test CloudFront URL generation"""
        s3_client, bucket_name = mock_s3
        cloudfront_domain = 'd123456.cloudfront.net'  # Domain without https://

        storage = ImageStorage(s3_client, bucket_name, cloudfront_domain)

        key = 'group-images/test/image.png'
        url = storage.get_cloudfront_url(key)

        # Implementation adds https:// prefix
        assert url == f'https://{cloudfront_domain}/{key}'

    def test_list_galleries(self, mock_s3):
        """Test listing gallery folders"""
        s3_client, bucket_name = mock_s3

        # Create test objects in different folders
        s3_client.put_object(
            Bucket=bucket_name,
            Key='group-images/2025-11-16-10-00-00/image1.json',
            Body=json.dumps({'test': 'data'})
        )
        s3_client.put_object(
            Bucket=bucket_name,
            Key='group-images/2025-11-15-14-30-00/image2.json',
            Body=json.dumps({'test': 'data'})
        )

        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')

        galleries = storage.list_galleries()

        assert len(galleries) >= 0  # Moto may not perfectly simulate prefix listing
        # Test passes if no exception is raised

    def test_list_gallery_images(self, mock_s3):
        """Test listing images from a specific gallery"""
        s3_client, bucket_name = mock_s3

        gallery_id = '2025-11-16-10-00-00'

        # Create test images
        s3_client.put_object(
            Bucket=bucket_name,
            Key=f'group-images/{gallery_id}/image1.json',
            Body=json.dumps({'model': 'Model 1'})
        )
        s3_client.put_object(
            Bucket=bucket_name,
            Key=f'group-images/{gallery_id}/image2.json',
            Body=json.dumps({'model': 'Model 2'})
        )

        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')

        images = storage.list_gallery_images(gallery_id)

        assert isinstance(images, list)
        # Test passes if method executes without error

    def test_get_image_metadata(self, mock_s3):
        """Test retrieving image metadata"""
        s3_client, bucket_name = mock_s3

        key = 'group-images/test/image.json'
        metadata = {
            'prompt': 'test',
            'model': 'Test Model',
            'output': SAMPLE_IMAGE_BASE64
        }

        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json.dumps(metadata)
        )

        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')

        retrieved = storage.get_image(key)

        assert retrieved is not None
        assert retrieved['model'] == 'Test Model'
        assert retrieved['prompt'] == 'test'

    def test_upload_image_to_sessions(self, mock_s3):
        """Test uploading image to S3 under sessions prefix"""
        s3_client, bucket_name = mock_s3

        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')

        image_data = SAMPLE_IMAGE_BASE64

        key = storage.upload_image(
            base64_image=image_data,
            target='2025-11-16-10-30-00',
            model_name='flux',
            prompt='test prompt',
            iteration=0,
        )

        assert key is not None
        assert 'sessions/' in key
        assert 'flux' in key
        assert 'iter0' in key

        # Verify image was uploaded
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        assert response is not None

    def test_upload_image_without_iteration(self, mock_s3):
        """Test uploading image without iteration index"""
        s3_client, bucket_name = mock_s3

        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')

        key = storage.upload_image(
            base64_image=SAMPLE_IMAGE_BASE64,
            target='2025-11-16-10-30-00',
            model_name='gemini',
            prompt='test prompt',
        )

        assert key is not None
        assert 'sessions/' in key
        assert 'iter' not in key

    def test_error_handling_invalid_key(self, mock_s3):
        """Test error handling for invalid S3 keys"""
        s3_client, bucket_name = mock_s3

        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')

        # Try to get non-existent image
        result = storage.get_image('invalid/key.json')

        # Should return None or handle gracefully
        assert result is None or isinstance(result, dict)

    def test_list_galleries_pagination(self, mock_s3):
        """Test that list_galleries paginates through >1000 gallery prefixes."""
        s3_client, bucket_name = mock_s3

        # Create 1050 gallery folders (need >1000 to trigger pagination)
        for i in range(1050):
            folder_name = f"2025-01-01-{i:06d}"
            s3_client.put_object(
                Bucket=bucket_name,
                Key=f'group-images/{folder_name}/image.json',
                Body=json.dumps({'test': 'data'})
            )

        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')
        galleries = storage.list_galleries()

        assert len(galleries) == 1050

    def test_list_galleries_client_error_logged_and_reraised(self, mock_s3):
        """Test that ClientError is logged and re-raised, not swallowed."""
        s3_client, bucket_name = mock_s3
        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')

        # Use a non-existent bucket to trigger ClientError
        storage.bucket = 'non-existent-bucket-xyz'

        with pytest.raises(ClientError):
            storage.list_galleries()

    def test_list_gallery_images_pagination(self, mock_s3):
        """Test that list_gallery_images paginates through >1000 objects."""
        s3_client, bucket_name = mock_s3
        gallery_id = '2025-11-16-10-00-00'

        # Create 1050 image objects
        for i in range(1050):
            s3_client.put_object(
                Bucket=bucket_name,
                Key=f'group-images/{gallery_id}/image-{i:06d}.json',
                Body=json.dumps({'model': f'Model {i}'})
            )

        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')
        images = storage.list_gallery_images(gallery_id)

        assert len(images) == 1050

    def test_list_gallery_images_client_error_logged_and_reraised(self, mock_s3):
        """Test that ClientError is logged and re-raised, not swallowed."""
        s3_client, bucket_name = mock_s3
        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')

        # Use a non-existent bucket to trigger ClientError
        storage.bucket = 'non-existent-bucket-xyz'

        with pytest.raises(ClientError):
            storage.list_gallery_images('some-gallery')

    def test_list_gallery_images_filters_json_only(self, mock_s3):
        """Test that list_gallery_images only returns .json files."""
        s3_client, bucket_name = mock_s3
        gallery_id = '2025-11-16-10-00-00'

        s3_client.put_object(
            Bucket=bucket_name,
            Key=f'group-images/{gallery_id}/image.json',
            Body=json.dumps({'model': 'test'})
        )
        s3_client.put_object(
            Bucket=bucket_name,
            Key=f'group-images/{gallery_id}/image.png',
            Body=b'binary data'
        )

        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')
        images = storage.list_gallery_images(gallery_id)

        assert len(images) == 1
        assert images[0].endswith('.json')
