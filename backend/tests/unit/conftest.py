"""
Pytest configuration and fixtures for backend unit tests
"""

import pytest
from moto import mock_aws
import boto3


@pytest.fixture
def mock_s3():
    """Mock S3 client for testing storage operations"""
    with mock_aws():
        # Create mock S3 client
        s3 = boto3.client('s3', region_name='us-east-1')

        # Create test bucket
        bucket_name = 'test-pixel-prompt-bucket'
        s3.create_bucket(Bucket=bucket_name)

        yield s3, bucket_name


@pytest.fixture
def mock_model_config():
    """Sample model configuration for testing"""
    return {
        'name': 'Test Model',
        'key': 'test-api-key-12345',
        'provider': 'openai'
    }


@pytest.fixture
def sample_prompt():
    """Sample prompt for testing"""
    return "A beautiful sunset over mountains"


@pytest.fixture
def sample_params():
    """Sample generation parameters"""
    return {
        'steps': 28,
        'guidance': 5.0,
        'control': 1.0
    }
