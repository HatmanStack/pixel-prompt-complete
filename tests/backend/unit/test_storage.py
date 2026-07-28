"""
Unit tests for storage utilities
"""

import json
from unittest.mock import patch

import pytest
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

        key = 'sessions/test/image.png'
        url = storage.get_cloudfront_url(key)

        # Implementation adds https:// prefix
        assert url == f'https://{cloudfront_domain}/{key}'

    def test_list_galleries(self, mock_s3):
        """Test listing gallery folders"""
        s3_client, bucket_name = mock_s3

        # Create test objects in different folders
        s3_client.put_object(
            Bucket=bucket_name,
            Key='sessions/2025-11-16-10-00-00/image1.json',
            Body=json.dumps({'test': 'data'})
        )
        s3_client.put_object(
            Bucket=bucket_name,
            Key='sessions/2025-11-15-14-30-00/image2.json',
            Body=json.dumps({'test': 'data'})
        )

        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')

        galleries = storage.list_galleries()

        assert len(galleries) == 2

    def test_list_galleries_excludes_session_uuid_folders(self, mock_s3):
        """Test that list_galleries filters out session UUID folders."""
        s3_client, bucket_name = mock_s3

        # Create a timestamp gallery folder
        s3_client.put_object(
            Bucket=bucket_name,
            Key='sessions/2025-11-16-10-00-00/image1.json',
            Body=json.dumps({'test': 'data'})
        )
        # Create a session UUID folder (should be excluded)
        s3_client.put_object(
            Bucket=bucket_name,
            Key='sessions/3f2504e0-4f89-11d3-9a0c-0305e82c3301/status.json',
            Body=json.dumps({'status': 'completed'})
        )

        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')

        galleries = storage.list_galleries()

        assert len(galleries) == 1
        assert galleries[0] == '2025-11-16-10-00-00'

    def test_list_gallery_images(self, mock_s3):
        """Test listing images from a specific gallery"""
        s3_client, bucket_name = mock_s3

        gallery_id = '2025-11-16-10-00-00'

        # Create test images
        s3_client.put_object(
            Bucket=bucket_name,
            Key=f'sessions/{gallery_id}/image1.json',
            Body=json.dumps({'model': 'Model 1'})
        )
        s3_client.put_object(
            Bucket=bucket_name,
            Key=f'sessions/{gallery_id}/image2.json',
            Body=json.dumps({'model': 'Model 2'})
        )

        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')

        images = storage.list_gallery_images(gallery_id)

        assert len(images) == 2

    def test_get_image_metadata(self, mock_s3):
        """Test retrieving image metadata"""
        s3_client, bucket_name = mock_s3

        key = 'sessions/test/image.json'
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
        """Test uploading image to S3 under sessions prefix as raw PNG"""
        s3_client, bucket_name = mock_s3

        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')

        image_data = SAMPLE_IMAGE_BASE64

        key = storage.upload_image(
            base64_image=image_data,
            target='2025-11-16-10-30-00',
            model_name='flux',

            iteration=0,
        )

        assert key is not None
        assert key.endswith('.png')
        assert 'sessions/' in key
        assert 'flux' in key
        assert 'iter0' in key

        # Verify image was uploaded as raw bytes
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        assert response is not None
        assert response['ContentType'] == 'image/png'

    def test_upload_image_without_iteration(self, mock_s3):
        """Test uploading image without iteration index"""
        s3_client, bucket_name = mock_s3

        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')

        key = storage.upload_image(
            base64_image=SAMPLE_IMAGE_BASE64,
            target='2025-11-16-10-30-00',
            model_name='gemini',

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
            h, remainder = divmod(i, 3600)
            m, s = divmod(remainder, 60)
            folder_name = f"2025-01-01-{h:02d}-{m:02d}-{s:02d}"
            s3_client.put_object(
                Bucket=bucket_name,
                Key=f'sessions/{folder_name}/image.json',
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

        with patch('utils.storage.StructuredLogger') as mock_logger:
            with pytest.raises(ClientError):
                storage.list_galleries()
            mock_logger.error.assert_called_once()
            assert 'Failed to list galleries' in mock_logger.error.call_args[0][0]

    def test_list_gallery_images_pagination(self, mock_s3):
        """Test that list_gallery_images paginates through >1000 objects."""
        s3_client, bucket_name = mock_s3
        gallery_id = '2025-11-16-10-00-00'

        # Create 1050 image objects
        for i in range(1050):
            s3_client.put_object(
                Bucket=bucket_name,
                Key=f'sessions/{gallery_id}/image-{i:06d}.json',
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

        with patch('utils.storage.StructuredLogger') as mock_logger:
            with pytest.raises(ClientError):
                storage.list_gallery_images('some-gallery')
            mock_logger.error.assert_called_once()
            assert 'Failed to list gallery images' in mock_logger.error.call_args[0][0]

    def test_list_gallery_images_includes_json_and_png(self, mock_s3):
        """Test that list_gallery_images returns both .json and .png files."""
        s3_client, bucket_name = mock_s3
        gallery_id = '2025-11-16-10-00-00'

        s3_client.put_object(
            Bucket=bucket_name,
            Key=f'sessions/{gallery_id}/image.json',
            Body=json.dumps({'model': 'test'})
        )
        s3_client.put_object(
            Bucket=bucket_name,
            Key=f'sessions/{gallery_id}/image.png',
            Body=b'binary data'
        )
        # Non-image files should be excluded
        s3_client.put_object(
            Bucket=bucket_name,
            Key=f'sessions/{gallery_id}/notes.txt',
            Body=b'some text'
        )

        storage = ImageStorage(s3_client, bucket_name, 'https://cdn.example.com')
        images = storage.list_gallery_images(gallery_id)

        assert len(images) == 2
        extensions = {img.rsplit('.', 1)[-1] for img in images}
        assert extensions == {'json', 'png'}


class TestGalleryHelpers:
    """Tests for validate_gallery_id and get_image_metadata helpers."""

    def test_validate_gallery_id_valid(self, mock_s3):
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, 'cdn.example.com')
        assert storage.validate_gallery_id('2025-11-15-14-30-45') is True

    def test_validate_gallery_id_invalid_format(self, mock_s3):
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, 'cdn.example.com')
        assert storage.validate_gallery_id('not-a-timestamp') is False
        assert storage.validate_gallery_id('') is False
        assert storage.validate_gallery_id('../../etc/passwd') is False

    def test_get_image_metadata_excludes_output(self, mock_s3):
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, 'cdn.example.com')
        key = 'sessions/2025-11-15-10-00-00/test.json'
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps({'output': 'BIG_BASE64_BLOB', 'model': 'gemini', 'prompt': 'p'}),
        )
        metadata = storage.get_image_metadata(key)
        assert metadata is not None
        assert 'output' not in metadata
        assert metadata['model'] == 'gemini'

    def test_get_image_metadata_missing(self, mock_s3):
        s3, bucket = mock_s3
        storage = ImageStorage(s3, bucket, 'cdn.example.com')
        assert storage.get_image_metadata('sessions/missing.json') is None


class TestListGalleriesBound:
    """list_galleries gained a limit and a cursor so the handler can stop
    expanding folders it will not return."""

    @staticmethod
    def _seed(s3_client, bucket_name, count=30):
        for i in range(count):
            folder = f"2026-02-01-00-00-{i:02d}"
            s3_client.put_object(
                Bucket=bucket_name, Key=f"sessions/{folder}/img.png", Body=b"x"
            )
        from utils.storage import ImageStorage

        return ImageStorage(s3_client, bucket_name, "cdn.example.com")

    def test_no_limit_returns_everything_as_before(self, mock_s3):
        s3_client, bucket_name = mock_s3
        storage = self._seed(s3_client, bucket_name)

        assert len(storage.list_galleries()) == 30

    def test_a_limit_returns_the_newest_n(self, mock_s3):
        s3_client, bucket_name = mock_s3
        storage = self._seed(s3_client, bucket_name)

        got = storage.list_galleries(limit=5)

        assert got == [
            "2026-02-01-00-00-29",
            "2026-02-01-00-00-28",
            "2026-02-01-00-00-27",
            "2026-02-01-00-00-26",
            "2026-02-01-00-00-25",
        ]

    def test_a_cursor_excludes_the_cursor_itself_and_everything_newer(self, mock_s3):
        """Strictly less than, or the client re-renders the folder it paged from."""
        s3_client, bucket_name = mock_s3
        storage = self._seed(s3_client, bucket_name)

        got = storage.list_galleries(limit=3, cursor="2026-02-01-00-00-25")

        assert got == [
            "2026-02-01-00-00-24",
            "2026-02-01-00-00-23",
            "2026-02-01-00-00-22",
        ]

    def test_a_cursor_past_the_oldest_folder_returns_nothing(self, mock_s3):
        s3_client, bucket_name = mock_s3
        storage = self._seed(s3_client, bucket_name)

        assert storage.list_galleries(limit=5, cursor="2026-02-01-00-00-00") == []

    def test_paging_the_whole_set_yields_each_folder_exactly_once(self, mock_s3):
        s3_client, bucket_name = mock_s3
        storage = self._seed(s3_client, bucket_name)

        seen = []
        cursor = None
        # Bounded rather than `while True`: a cursor that is inclusive rather
        # than exclusive re-returns the folder it paged from forever, and a
        # test that hangs is worse evidence than one that fails.
        for _ in range(10):
            page = storage.list_galleries(limit=7, cursor=cursor)
            if not page:
                break
            seen.extend(page)
            cursor = page[-1]
        else:
            raise AssertionError("paging did not terminate within 10 pages of 30 folders")

        assert len(seen) == 30
        assert len(set(seen)) == 30
        assert seen == sorted(seen, reverse=True)
