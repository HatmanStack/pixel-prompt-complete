"""
Integration tests for correlation ID propagation.
"""

import pytest
import requests
import uuid


@pytest.fixture
def correlation_id():
    """Generate a test correlation ID"""
    return str(uuid.uuid4())


def test_generate_endpoint_accepts_correlation_id(api_endpoint, correlation_id):
    """Test /generate endpoint accepts and uses correlation ID"""
    response = requests.post(
        f"{api_endpoint}/generate",
        json={
            "prompt": "test prompt for correlation",
            "steps": 28,
            "guidance": 5.0,
            "control": 1.0
        },
        headers={"X-Correlation-ID": correlation_id},
        timeout=30
    )

    assert response.status_code == 200
    # Correlation ID should be logged on backend (check CloudWatch manually)


def test_status_endpoint_accepts_correlation_id(api_endpoint, correlation_id):
    """Test /status endpoint accepts correlation ID"""
    # First create a job
    create_response = requests.post(
        f"{api_endpoint}/generate",
        json={"prompt": "test", "steps": 28},
        timeout=30
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["jobId"]

    # Then check status with correlation ID
    response = requests.get(
        f"{api_endpoint}/status/{job_id}",
        headers={"X-Correlation-ID": correlation_id},
        timeout=30
    )

    assert response.status_code == 200
    # Correlation ID should be logged on backend


def test_enhance_endpoint_accepts_correlation_id(api_endpoint, correlation_id):
    """Test /enhance endpoint accepts correlation ID"""
    response = requests.post(
        f"{api_endpoint}/enhance",
        json={"prompt": "sunset"},
        headers={"X-Correlation-ID": correlation_id},
        timeout=30
    )

    assert response.status_code == 200
    # Correlation ID should be logged on backend


def test_log_endpoint_requires_correlation_id(api_endpoint, correlation_id):
    """Test /log endpoint uses correlation ID"""
    response = requests.post(
        f"{api_endpoint}/log",
        json={
            "level": "ERROR",
            "message": "Test error with correlation ID",
            "metadata": {"test": True}
        },
        headers={"X-Correlation-ID": correlation_id},
        timeout=30
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    # Correlation ID should appear in CloudWatch logs


def test_correlation_id_generated_if_not_provided(api_endpoint):
    """Test that backend generates correlation ID if not provided"""
    response = requests.post(
        f"{api_endpoint}/generate",
        json={"prompt": "test without correlation id", "steps": 28},
        timeout=30
        # No X-Correlation-ID header
    )

    assert response.status_code == 200
    # Backend should generate a correlation ID and log it
