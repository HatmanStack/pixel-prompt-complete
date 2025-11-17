"""
Integration tests for Pixel Prompt Complete API endpoints.

These tests require a deployed backend or local SAM environment.
Run with: pytest tests/integration/test_api_endpoints.py -v

Prerequisites:
- Set API_ENDPOINT environment variable to your deployed API
- Or run `sam local start-api` for local testing
"""

import os
import pytest
import requests
import time
import json

# Load API endpoint from environment
API_ENDPOINT = os.environ.get('API_ENDPOINT', 'http://localhost:3000')

# Timeout for all HTTP requests (in seconds)
REQUEST_TIMEOUT = 30


class TestHealthAndBasicEndpoints:
    """Test basic API health and routing."""

    def test_404_on_invalid_route(self):
        """Test that invalid routes return 404."""
        response = requests.get(f"{API_ENDPOINT}/invalid-route", timeout=REQUEST_TIMEOUT)
        assert response.status_code == 404
        data = response.json()
        assert 'error' in data
        assert data['error'] == 'Not found'

    def test_cors_headers_present(self):
        """Test that CORS headers are configured."""
        response = requests.get(f"{API_ENDPOINT}/invalid-route", timeout=REQUEST_TIMEOUT)
        assert 'Access-Control-Allow-Origin' in response.headers
        assert response.headers['Access-Control-Allow-Origin'] == '*'


class TestPromptEnhancement:
    """Test prompt enhancement endpoint."""

    def test_enhance_valid_prompt(self):
        """Test enhancing a valid prompt."""
        response = requests.post(
            f"{API_ENDPOINT}/enhance",
            json={'prompt': 'cat'},
            headers={'Content-Type': 'application/json'},
            timeout=REQUEST_TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()
        assert 'original' in data
        assert 'enhanced' in data
        assert data['original'] == 'cat'
        assert len(data['enhanced']) > len(data['original'])

    def test_enhance_empty_prompt(self):
        """Test that empty prompts are rejected."""
        response = requests.post(
            f"{API_ENDPOINT}/enhance",
            json={'prompt': ''},
            headers={'Content-Type': 'application/json'},
            timeout=REQUEST_TIMEOUT
        )

        assert response.status_code == 400
        data = response.json()
        assert 'error' in data

    def test_enhance_missing_prompt(self):
        """Test that missing prompt field is rejected."""
        response = requests.post(
            f"{API_ENDPOINT}/enhance",
            json={},
            headers={'Content-Type': 'application/json'},
            timeout=REQUEST_TIMEOUT
        )

        assert response.status_code == 400

    def test_enhance_too_long_prompt(self):
        """Test that prompts exceeding max length are rejected."""
        long_prompt = 'a' * 501  # Max is 500 for enhancement
        response = requests.post(
            f"{API_ENDPOINT}/enhance",
            json={'prompt': long_prompt},
            headers={'Content-Type': 'application/json'},
            timeout=REQUEST_TIMEOUT
        )

        assert response.status_code == 400


class TestGalleryEndpoints:
    """Test gallery listing and detail endpoints."""

    def test_gallery_list(self):
        """Test listing all galleries."""
        response = requests.get(f"{API_ENDPOINT}/gallery/list", timeout=REQUEST_TIMEOUT)

        assert response.status_code == 200
        data = response.json()
        assert 'galleries' in data
        assert 'total' in data
        assert isinstance(data['galleries'], list)

    def test_gallery_detail_invalid_id(self):
        """Test gallery detail with invalid ID."""
        response = requests.get(f"{API_ENDPOINT}/gallery/invalid-id-12345", timeout=REQUEST_TIMEOUT)

        # Should return 200 with empty images (gallery doesn't exist)
        assert response.status_code == 200
        data = response.json()
        assert 'galleryId' in data
        assert 'images' in data
        assert isinstance(data['images'], list)


@pytest.mark.slow
class TestImageGeneration:
    """Test full image generation workflow.

    Note: These tests are slow as they involve actual AI model calls.
    Mark as @pytest.mark.slow and run separately.
    """

    def test_generate_job_creation(self):
        """Test creating an image generation job."""
        response = requests.post(
            f"{API_ENDPOINT}/generate",
            json={
                'prompt': 'test image',
                'steps': 25,
                'guidance': 7,
                'ip': '127.0.0.1'
            },
            headers={'Content-Type': 'application/json'},
            timeout=REQUEST_TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()
        assert 'jobId' in data
        assert 'message' in data
        assert 'totalModels' in data

    def test_job_status_check(self):
        """Test checking job status."""
        # First create a job
        create_response = requests.post(
            f"{API_ENDPOINT}/generate",
            json={
                'prompt': 'test status check',
                'steps': 25,
                'guidance': 7,
                'ip': '127.0.0.1'
            },
            headers={'Content-Type': 'application/json'},
            timeout=REQUEST_TIMEOUT
        )

        assert create_response.status_code == 200
        job_id = create_response.json()['jobId']

        # Check status
        status_response = requests.get(f"{API_ENDPOINT}/status/{job_id}", timeout=REQUEST_TIMEOUT)

        assert status_response.status_code == 200
        status_data = status_response.json()
        assert 'jobId' in status_data
        assert 'status' in status_data
        assert 'results' in status_data
        assert status_data['jobId'] == job_id

    def test_invalid_job_id(self):
        """Test status check with invalid job ID."""
        response = requests.get(f"{API_ENDPOINT}/status/invalid-job-id", timeout=REQUEST_TIMEOUT)

        # Should return 404 for non-existent job
        assert response.status_code == 404


class TestInputValidation:
    """Test input validation and security."""

    def test_generate_empty_prompt(self):
        """Test that empty prompts are rejected."""
        response = requests.post(
            f"{API_ENDPOINT}/generate",
            json={'prompt': '', 'steps': 25, 'guidance': 7},
            headers={'Content-Type': 'application/json'},
            timeout=REQUEST_TIMEOUT
        )

        assert response.status_code == 400

    def test_generate_too_long_prompt(self):
        """Test that prompts exceeding max length are rejected."""
        long_prompt = 'a' * 1001  # Max is 1000
        response = requests.post(
            f"{API_ENDPOINT}/generate",
            json={'prompt': long_prompt, 'steps': 25, 'guidance': 7},
            headers={'Content-Type': 'application/json'},
            timeout=REQUEST_TIMEOUT
        )

        assert response.status_code == 400

    def test_invalid_json(self):
        """Test that invalid JSON is rejected."""
        response = requests.post(
            f"{API_ENDPOINT}/generate",
            data='invalid json{',
            headers={'Content-Type': 'application/json'},
            timeout=REQUEST_TIMEOUT
        )

        assert response.status_code == 400


# Configuration for pytest
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
