"""Unit tests for retry logic and the SDK client caches.

On the client-cache tests below: **they do not spawn threads.** The defect
being fixed is that three module-level dicts were read and written by four
concurrent generation threads with no lock while ``firefly.py`` guarded its
equivalent cache with an explicit one. A threaded test here would race
itself -- a pass would prove the interleaving happened not to occur, not that
it cannot. The lock's presence is verifiable by reading; what is worth
asserting is the behaviour the lock must not change, which is cache identity.
Same reasoning as the moto rule in the plan's Phase-0.
"""

from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from utils.retry import (
    is_retryable_error,
    retry_with_backoff,
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

        with patch('utils.retry.time.sleep') as mock_sleep:
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

        with patch('utils.retry.time.sleep') as mock_sleep:
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
        """Test that correlation ID is passed to StructuredLogger"""
        mock_func = Mock()
        mock_func.side_effect = [
            ConnectionError("Network error"),
            "success"
        ]

        with patch('utils.retry.StructuredLogger') as mock_logger:
            decorated = retry_with_backoff(
                max_retries=3,
                base_delay=0.01,
                correlation_id="test-correlation-123"
            )(mock_func)

            result = decorated()

            assert result == "success"
            assert mock_logger.warning.called
            call_kwargs = mock_logger.warning.call_args[1]
            assert call_kwargs.get('correlation_id') == "test-correlation-123"


class TestRetryMisconfiguration:
    """A negative max_retries must not replace the real failure with a TypeError.

    The loop body never ran, so ``last_exception`` was still None at the
    terminal ``raise last_exception`` and the caller got
    "TypeError: exceptions must derive from BaseException" instead of
    whatever actually went wrong.
    """

    def test_a_negative_max_retries_is_rejected_at_decoration(self):
        with pytest.raises(ValueError, match="max_retries"):
            retry_with_backoff(max_retries=-1)

    def test_the_error_names_the_parameter_and_the_bound(self):
        with pytest.raises(ValueError) as exc:
            retry_with_backoff(max_retries=-5)
        assert "max_retries" in str(exc.value)
        assert ">= 0" in str(exc.value)

    def test_decoration_time_not_call_time(self):
        """Failing at import beats failing on the first error in production."""
        with pytest.raises(ValueError):
            retry_with_backoff(max_retries=-1)

    def test_zero_retries_still_calls_the_function_exactly_once(self):
        """Confirming the existing semantics, since a decoration-time check
        could accidentally reject 0 along with the negatives."""
        calls = []

        @retry_with_backoff(max_retries=0)
        def _once():
            calls.append(1)
            return "ok"

        assert _once() == "ok"
        assert len(calls) == 1

    def test_zero_retries_raises_the_real_error_without_retrying(self):
        calls = []

        @retry_with_backoff(max_retries=0)
        def _fails():
            calls.append(1)
            raise ConnectionError("nope")

        with pytest.raises(ConnectionError, match="nope"):
            _fails()
        assert len(calls) == 1


class TestClientCacheIdentity:
    """The behaviour the lock must not change. See the module docstring for
    why there are no threads here."""

    def test_the_openai_cache_returns_the_same_instance_for_the_same_key(self):
        import utils.clients as c

        c._openai_clients.clear()
        first = c.get_openai_client("k")
        assert c.get_openai_client("k") is first

    def test_the_openai_cache_separates_different_keys(self):
        import utils.clients as c

        c._openai_clients.clear()
        assert c.get_openai_client("k1") is not c.get_openai_client("k2")

    def test_the_genai_cache_returns_the_same_instance_for_the_same_key(self):
        import utils.clients as c

        c._genai_clients.clear()
        first = c.get_genai_client("k", timeout=30.0)
        assert c.get_genai_client("k", timeout=30.0) is first
        assert c.get_genai_client("k", timeout=10.0) is not first

    def test_the_bedrock_cache_returns_the_same_instance_for_the_same_key(self):
        import utils.clients as c

        c._bedrock_clients.clear()
        first = c.get_bedrock_client("us-west-2")
        assert c.get_bedrock_client("us-west-2") is first
        assert c.get_bedrock_client("eu-west-1") is not first

    def test_every_cache_is_lock_guarded(self):
        """Three dicts mutated by four generation threads had no lock while
        firefly.py guarded its equivalent one. An inconsistency between two
        caches in the same codebase is itself a defect: the next reader
        cannot tell which pattern is intended."""
        import threading

        import utils.clients as c

        for name in ("_openai_lock", "_genai_lock", "_bedrock_lock"):
            assert isinstance(getattr(c, name), type(threading.Lock())), name
