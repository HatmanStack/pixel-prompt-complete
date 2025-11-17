"""
Retry Utility with Exponential Backoff.

Provides retry decorator for handling transient errors in S3 and external API calls.
"""

import time
import logging
from functools import wraps
from botocore.exceptions import ClientError, BotoCoreError


logger = logging.getLogger()


# Retryable S3 error codes
RETRYABLE_S3_ERRORS = {
    '503',  # SlowDown, Service Unavailable
    '500',  # InternalError
    'RequestTimeout',
    'RequestTimeoutException',
}

# Permanent S3 errors that should not be retried
PERMANENT_S3_ERRORS = {
    '403',  # Forbidden
    '404',  # NotFound
    '400',  # BadRequest
    'InvalidBucketName',
    'NoSuchBucket',
}


def is_retryable_error(error):
    """
    Determine if an error should be retried.

    Args:
        error: Exception object

    Returns:
        bool: True if error is retryable
    """
    # Network errors are retryable
    if isinstance(error, (ConnectionError, TimeoutError, BotoCoreError)):
        return True

    # Check S3 ClientError
    if isinstance(error, ClientError):
        error_code = error.response.get('Error', {}).get('Code', '')
        http_status = str(error.response.get('ResponseMetadata', {}).get('HTTPStatusCode', ''))

        # Don't retry permanent errors
        if error_code in PERMANENT_S3_ERRORS or http_status in PERMANENT_S3_ERRORS:
            return False

        # Retry specific error codes and status codes
        if error_code in RETRYABLE_S3_ERRORS or http_status in RETRYABLE_S3_ERRORS:
            return True

    return False


def retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=8.0, correlation_id=None):
    """
    Decorator for retrying functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (default 3)
        base_delay: Initial delay in seconds (default 1.0)
        max_delay: Maximum delay in seconds (default 8.0)
        correlation_id: Optional correlation ID for logging

    Returns:
        Decorated function with retry logic
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):  # +1 for initial attempt
                try:
                    return func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    # Check if error is retryable
                    if not is_retryable_error(e):
                        func_name = getattr(func, '__name__', 'unknown_function')
                        logger.warning(f"Non-retryable error in {func_name}: {e}")
                        raise

                    # Don't retry if this was the last attempt
                    if attempt >= max_retries:
                        func_name = getattr(func, '__name__', 'unknown_function')
                        logger.exception(
                            f"Max retries ({max_retries}) exceeded for {func_name}: {e}",
                            extra={'correlationId': correlation_id} if correlation_id else {}
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (2 ** attempt), max_delay)

                    func_name = getattr(func, '__name__', 'unknown_function')
                    logger.warning(
                        f"Retry {attempt + 1}/{max_retries} for {func_name} "
                        f"after {delay}s delay: {e}",
                        extra={'correlationId': correlation_id} if correlation_id else {}
                    )

                    time.sleep(delay)

            # Should never reach here, but raise last exception just in case
            raise last_exception

        return wrapper
    return decorator


# Convenience decorator with default settings
def retry_s3(correlation_id=None):
    """
    Convenience decorator for S3 operations with default retry settings.

    Args:
        correlation_id: Optional correlation ID for logging

    Returns:
        Decorated function with S3 retry logic
    """
    return retry_with_backoff(
        max_retries=3,
        base_delay=1.0,
        max_delay=4.0,
        correlation_id=correlation_id
    )
