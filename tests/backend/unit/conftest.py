"""
Pytest configuration and fixtures for backend unit tests
"""

import pytest
from moto import mock_aws
import boto3

from utils.rate_limit import reset_cache as reset_rate_limit_cache


def _reset_handler_singletons():
    """Clear module-level client caches in handlers to ensure test isolation."""
    import models.handlers as h
    h._openai_clients.clear()
    h._genai_clients.clear()
    h._bedrock_nova_client = None
    h._bedrock_sd_client = None


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Auto-reset handler singletons before each test."""
    _reset_handler_singletons()
    yield
    _reset_handler_singletons()


@pytest.fixture
def mock_s3():
    """Mock S3 client for testing storage operations"""
    # Reset rate limit cache before each test for isolation
    reset_rate_limit_cache()

    with mock_aws():
        # Create mock S3 client
        s3 = boto3.client('s3', region_name='us-east-1')

        # Create test bucket
        bucket_name = 'test-pixel-prompt-bucket'
        s3.create_bucket(Bucket=bucket_name)

        yield s3, bucket_name

    # Reset cache after test as well
    reset_rate_limit_cache()


@pytest.fixture
def mock_model_config():
    """Sample model configuration for testing (5-field format)"""
    return {
        'index': 1,
        'provider': 'openai',
        'id': 'dall-e-3',
        'api_key': 'test-api-key-12345'
    }


@pytest.fixture
def sample_prompt():
    """Sample prompt for testing"""
    return "A beautiful sunset over mountains"


@pytest.fixture
def sample_params():
    """Sample generation parameters"""
    return {'control': 1.0
    }
