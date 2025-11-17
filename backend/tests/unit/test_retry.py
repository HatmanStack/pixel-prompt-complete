"""
Unit tests for retry logic.
"""

import pytest
import time
from unittest.mock import Mock, patch
from botocore.exceptions import ClientError, BotoCoreError
from src.utils.retry import (
    retry_with_backoff,
    is_retryable_error,
    RETRYABLE_S3_ERRORS,
    PERMANENT_S3_ERRORS
)


class TestRetryableErrorDetection:
    """Tests for is_retryable_error function"""

    def test_network_errors_are_retryable(self):
        """Test that network errors are retryable"""
        assert is_retryable_error(ConnectionError("Connection failed"))
        assert is_retryable_error(TimeoutError("Request timeout"))
        assert is_retryable_error(BotoCoreError())

    def test_permanent_s3_errors_not_retryable(self):
        """Test that permanent S3 errors are not retryable"""
        # 403 Forbidden
        error_403 = ClientError(
            {'Error': {'Code': 'AccessDenied'}, 'ResponseMetadata': {'HTTPStatusCode': 403}},
            'GetObject'
        )
        assert not is_retryable_error(error_403)

        # 404 NotFound
        error_404 = ClientError(
            {'Error': {'Code': 'NoSuchKey'}, 'ResponseMetadata': {'HTTPStatusCode': 404}},
            'GetObject'
        )
        assert not is_retryable_error(error_404)

    def test_transient_s3_errors_are_retryable(self):
        """Test that transient S3 errors are retryable"""
        # 503 Service Unavailable
        error_503 = ClientError(
            {'Error': {'Code': 'SlowDown'}, 'ResponseMetadata': {'HTTPStatusCode': 503}},
            'PutObject'
        )
        assert is_retryable_error(error_503)

        # 500 Internal Error
        error_500 = ClientError(
            {'Error': {'Code': 'InternalError'}, 'ResponseMetadata': {'HTTPStatusCode': 500}},
            'PutObject'
        )
        assert is_retryable_error(error_500)

    def test_unknown_errors_not_retryable(self):
        """Test that unknown errors are not retried by default"""
        unknown_error = ValueError("Unknown error")
        assert not is_retryable_error(unknown_error)


class TestRetryDecorator:
    """Tests for retry_with_backoff decorator"""

    def test_successful_call_no_retry(self):
        """Test that successful calls don't retry"""
        mock_func = Mock(return_value="success")
        decorated = retry_with_backoff(max_retries=3)(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 1

    def test_retry_on_retryable_error(self):
        """Test that retryable errors trigger retries"""
        mock_func = Mock()
        # Fail twice, then succeed
        mock_func.side_effect = [
            ConnectionError("Network error"),
            ConnectionError("Network error"),
            "success"
        ]

        decorated = retry_with_backoff(max_retries=3, base_delay=0.01)(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 3

    def test_max_retries_exhausted(self):
        """Test that max retries are respected"""
        mock_func = Mock()
        # Always fail with retryable error
        mock_func.side_effect = ConnectionError("Network error")

        decorated = retry_with_backoff(max_retries=3, base_delay=0.01)(mock_func)

        with pytest.raises(ConnectionError):
            decorated()

        # Initial call + 3 retries = 4 calls total
        assert mock_func.call_count == 4

    def test_permanent_error_no_retry(self):
        """Test that permanent errors don't retry"""
        mock_func = Mock()
        permanent_error = ClientError(
            {'Error': {'Code': 'AccessDenied'}, 'ResponseMetadata': {'HTTPStatusCode': 403}},
            'GetObject'
        )
        mock_func.side_effect = permanent_error

        decorated = retry_with_backoff(max_retries=3)(mock_func)

        with pytest.raises(ClientError):
            decorated()

        # Should only call once (no retries)
        assert mock_func.call_count == 1

    def test_exponential_backoff_delay(self):
        """Test that exponential backoff delays are applied"""
        mock_func = Mock()
        mock_func.side_effect = [
            ConnectionError("Error 1"),
            ConnectionError("Error 2"),
            "success"
        ]

        with patch('src.utils.retry.time.sleep') as mock_sleep:
            decorated = retry_with_backoff(max_retries=3, base_delay=0.1, max_delay=1.0)(mock_func)
            result = decorated()

        assert result == "success"
        # Should have delays of 0.1s and 0.2s
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(0.1)
        mock_sleep.assert_any_call(0.2)

    def test_max_delay_cap(self):
        """Test that max delay caps exponential growth"""
        mock_func = Mock()
        mock_func.side_effect = [
            ConnectionError("Error"),
            ConnectionError("Error"),
            ConnectionError("Error"),
            "success"
        ]

        with patch('src.utils.retry.time.sleep') as mock_sleep:
            decorated = retry_with_backoff(
                max_retries=4,
                base_delay=0.1,
                max_delay=0.2  # Cap at 0.2s
            )(mock_func)
            result = decorated()

        assert result == "success"
        # Delays should respect the cap: 0.1, 0.2, 0.2
        assert mock_sleep.call_count == 3
        calls = [call[0][0] for call in mock_sleep.call_args_list]
        assert calls == [0.1, 0.2, 0.2]

    def test_correlation_id_logging(self):
        """Test that correlation ID is included in logs"""
        mock_func = Mock()
        mock_func.side_effect = [
            ConnectionError("Network error"),
            "success"
        ]

        with patch('src.utils.retry.logger') as mock_logger:
            decorated = retry_with_backoff(
                max_retries=3,
                base_delay=0.01,
                correlation_id="test-correlation-123"
            )(mock_func)

            result = decorated()

            assert result == "success"
            # Check that warning was logged with correlation ID
            assert mock_logger.warning.called
            call_args = mock_logger.warning.call_args
            assert 'correlationId' in call_args[1].get('extra', {})
            assert call_args[1]['extra']['correlationId'] == "test-correlation-123"
