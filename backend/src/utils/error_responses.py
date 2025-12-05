"""
Standardized Error Response Utilities.

Provides consistent error response format across all API endpoints.
"""

from typing import Optional, Dict, Any


def error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: Optional[str] = None,
    retry_after: Optional[int] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Create standardized error response.

    Args:
        status_code: HTTP status code
        error_code: Error code identifier (e.g., "RATE_LIMIT_EXCEEDED")
        message: User-friendly error message
        details: Optional detailed error information
        retry_after: Optional retry-after time in seconds
        **kwargs: Additional error metadata

    Returns:
        Dict containing standardized error response
    """
    response = {
        "error": error_code,
        "message": message,
    }

    if details:
        response["details"] = details

    if retry_after is not None:
        response["retryAfter"] = retry_after

    # Add any additional metadata
    if kwargs:
        response.update(kwargs)

    return response


def rate_limit_exceeded(retry_after: int, limit_type: str = "requests", **kwargs) -> Dict[str, Any]:
    """429 Rate Limit Exceeded"""
    minutes = (retry_after + 59) // 60  # Round up to nearest minute

    return error_response(
        status_code=429,
        error_code="RATE_LIMIT_EXCEEDED",
        message=f"Rate limit exceeded. Please try again in {minutes} minute{'s' if minutes != 1 else ''}.",
        details=f"Too many {limit_type}. Please wait and try again.",
        retry_after=retry_after,
        **kwargs
    )


def internal_server_error(message: str = "Internal server error", **kwargs) -> Dict[str, Any]:
    """500 Internal Server Error"""
    return error_response(
        status_code=500,
        error_code="INTERNAL_SERVER_ERROR",
        message=message,
        **kwargs
    )


# Specific application errors

def inappropriate_content(**kwargs) -> Dict[str, Any]:
    """Content filtered for inappropriate content"""
    return error_response(
        status_code=400,
        error_code="INAPPROPRIATE_CONTENT",
        message="Your prompt contains inappropriate content and cannot be processed.",
        details="Please revise your prompt to remove inappropriate content.",
        **kwargs
    )


def prompt_required(**kwargs) -> Dict[str, Any]:
    """Prompt is required"""
    return error_response(
        status_code=400,
        error_code="PROMPT_REQUIRED",
        message="Prompt is required",
        details="Please provide a text prompt to generate images.",
        **kwargs
    )


def prompt_too_long(max_length: int = 1000, **kwargs) -> Dict[str, Any]:
    """Prompt exceeds maximum length"""
    return error_response(
        status_code=400,
        error_code="PROMPT_TOO_LONG",
        message=f"Prompt is too long (maximum {max_length} characters)",
        details=f"Please shorten your prompt to {max_length} characters or less.",
        maxLength=max_length,
        **kwargs
    )


def invalid_json(**kwargs) -> Dict[str, Any]:
    """Invalid JSON in request body"""
    return error_response(
        status_code=400,
        error_code="INVALID_JSON",
        message="Invalid JSON in request body",
        details="The request body contains invalid JSON. Please check the format and try again.",
        **kwargs
    )


def job_not_found(job_id: str, **kwargs) -> Dict[str, Any]:
    """Job not found"""
    return error_response(
        status_code=404,
        error_code="JOB_NOT_FOUND",
        message="Job not found",
        details=f"The job with ID '{job_id}' could not be found. It may have expired.",
        jobId=job_id,
        **kwargs
    )
