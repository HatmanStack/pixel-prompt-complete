"""
Standardized Error Response Utilities.

Provides consistent error response format across all API endpoints.
"""

from typing import Any, Dict, Optional


def error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: Optional[str] = None,
    retry_after: Optional[int] = None,
    **kwargs,
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
        **kwargs,
    )


def internal_server_error(message: str = "Internal server error", **kwargs) -> Dict[str, Any]:
    """500 Internal Server Error"""
    return error_response(
        status_code=500, error_code="INTERNAL_SERVER_ERROR", message=message, **kwargs
    )


# Specific application errors


def inappropriate_content(**kwargs) -> Dict[str, Any]:
    """Content filtered for inappropriate content"""
    return error_response(
        status_code=400,
        error_code="INAPPROPRIATE_CONTENT",
        message="Your prompt contains inappropriate content and cannot be processed.",
        details="Please revise your prompt to remove inappropriate content.",
        **kwargs,
    )


def prompt_required(**kwargs) -> Dict[str, Any]:
    """Prompt is required"""
    return error_response(
        status_code=400,
        error_code="PROMPT_REQUIRED",
        message="Prompt is required",
        details="Please provide a text prompt to generate images.",
        **kwargs,
    )


def prompt_too_long(max_length: int = 1000, **kwargs) -> Dict[str, Any]:
    """Prompt exceeds maximum length"""
    return error_response(
        status_code=400,
        error_code="PROMPT_TOO_LONG",
        message=f"Prompt is too long (maximum {max_length} characters)",
        details=f"Please shorten your prompt to {max_length} characters or less.",
        maxLength=max_length,
        **kwargs,
    )


def auth_required(**kwargs) -> Dict[str, Any]:
    """401 Authentication required."""
    return error_response(
        status_code=401,
        error_code="AUTH_REQUIRED",
        message="Authentication required",
        **kwargs,
    )


def tier_quota_exceeded(tier: str, reset_at: int, **kwargs) -> Dict[str, Any]:
    """429 Quota exceeded for a tier."""
    return error_response(
        status_code=429,
        error_code="TIER_QUOTA_EXCEEDED",
        message=f"Quota exceeded for {tier} tier",
        tier=tier,
        resetAt=reset_at,
        **kwargs,
    )


def subscription_required(**kwargs) -> Dict[str, Any]:
    """402 Paid subscription required."""
    return error_response(
        status_code=402,
        error_code="SUBSCRIPTION_REQUIRED",
        message="Paid subscription required",
        **kwargs,
    )


def guest_global_limit(**kwargs) -> Dict[str, Any]:
    """429 Global guest traffic limit reached."""
    return error_response(
        status_code=429,
        error_code="GUEST_GLOBAL_LIMIT",
        message="Guest traffic limit reached, please sign in",
        **kwargs,
    )


def invalid_json(**kwargs) -> Dict[str, Any]:
    """Invalid JSON in request body"""
    return error_response(
        status_code=400,
        error_code="INVALID_JSON",
        message="Invalid JSON in request body",
        details="The request body contains invalid JSON. Please check the format and try again.",
        **kwargs,
    )


def account_suspended(**kwargs) -> Dict[str, Any]:
    """403 Account suspended."""
    return error_response(
        status_code=403,
        error_code="ACCOUNT_SUSPENDED",
        message="Your account has been suspended. Contact support for assistance.",
        **kwargs,
    )


def model_cost_ceiling(**kwargs) -> Dict[str, Any]:
    """429 All models have reached their daily generation cap."""
    return error_response(
        status_code=429,
        error_code="MODEL_COST_CEILING",
        message="All models have reached their daily generation cap. Please try again tomorrow.",
        **kwargs,
    )


def captcha_required(**kwargs) -> Dict[str, Any]:
    """403 CAPTCHA verification required."""
    return error_response(
        status_code=403,
        error_code="CAPTCHA_REQUIRED",
        message="CAPTCHA verification required",
        **kwargs,
    )


def captcha_failed(**kwargs) -> Dict[str, Any]:
    """403 CAPTCHA verification failed."""
    return error_response(
        status_code=403,
        error_code="CAPTCHA_FAILED",
        message="CAPTCHA verification failed. Please try again.",
        **kwargs,
    )


def admin_required(**kwargs) -> Dict[str, Any]:
    """403 Admin access required."""
    return error_response(
        status_code=403,
        error_code="ADMIN_REQUIRED",
        message="Admin access required",
        **kwargs,
    )


def admin_disabled(**kwargs) -> Dict[str, Any]:
    """501 Admin features are disabled."""
    return error_response(
        status_code=501,
        error_code="ADMIN_DISABLED",
        message="Admin features are disabled",
        **kwargs,
    )
