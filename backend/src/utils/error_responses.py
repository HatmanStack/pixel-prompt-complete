"""
Standardized Error Response Utilities.

Provides consistent error response format across all API endpoints.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


def error_response(
    error_code: str,
    message: str,
    details: Optional[str] = None,
    retry_after: Optional[int] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Create standardized error response.

    Args:
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
        error_code="RATE_LIMIT_EXCEEDED",
        message=f"Rate limit exceeded. Please try again in {minutes} minute{'s' if minutes != 1 else ''}.",
        details=f"Too many {limit_type}. Please wait and try again.",
        retry_after=retry_after,
        **kwargs,
    )


def internal_server_error(message: str = "Internal server error", **kwargs) -> Dict[str, Any]:
    """500 Internal Server Error"""
    return error_response(error_code="INTERNAL_SERVER_ERROR", message=message, **kwargs)


# Specific application errors


def inappropriate_content(**kwargs) -> Dict[str, Any]:
    """400 Content filtered for inappropriate content"""
    return error_response(
        error_code="INAPPROPRIATE_CONTENT",
        message="Your prompt contains inappropriate content and cannot be processed.",
        details="Please revise your prompt to remove inappropriate content.",
        **kwargs,
    )


def prompt_required(**kwargs) -> Dict[str, Any]:
    """400 Prompt is required"""
    return error_response(
        error_code="PROMPT_REQUIRED",
        message="Prompt is required",
        details="Please provide a text prompt to generate images.",
        **kwargs,
    )


def prompt_too_long(max_length: int = 1000, **kwargs) -> Dict[str, Any]:
    """400 Prompt exceeds maximum length"""
    return error_response(
        error_code="PROMPT_TOO_LONG",
        message=f"Prompt is too long (maximum {max_length} characters)",
        details=f"Please shorten your prompt to {max_length} characters or less.",
        maxLength=max_length,
        **kwargs,
    )


def auth_required(**kwargs) -> Dict[str, Any]:
    """401 Authentication required."""
    return error_response(
        error_code="AUTH_REQUIRED",
        message="Authentication required",
        **kwargs,
    )


def tier_quota_exceeded(tier: str, reset_at: int, **kwargs) -> Dict[str, Any]:
    """429 Quota exceeded for a tier."""
    return error_response(
        error_code="TIER_QUOTA_EXCEEDED",
        message=f"Quota exceeded for {tier} tier",
        tier=tier,
        resetAt=reset_at,
        **kwargs,
    )


def insufficient_credits(
    tier: str, reset_at: int, remaining: int = 0, required: int = 0, **kwargs
) -> Dict[str, Any]:
    """402 Not enough credits left in the current allotment.

    402 rather than 429: this is not rate limiting, it is a depleted balance.
    The distinction matters to a client deciding whether to back off and retry
    (429) or to prompt the user to upgrade or wait for renewal (402).
    """
    return error_response(
        error_code="INSUFFICIENT_CREDITS",
        message=(
            f"Not enough credits remaining on the {tier} plan. "
            "Credits renew at the start of the next period."
        ),
        tier=tier,
        resetAt=reset_at,
        creditsRemaining=remaining,
        creditsRequired=required,
        **kwargs,
    )


def subscription_required(**kwargs) -> Dict[str, Any]:
    """402 Paid subscription required."""
    return error_response(
        error_code="SUBSCRIPTION_REQUIRED",
        message="Paid subscription required",
        **kwargs,
    )


def guest_ip_limit(**kwargs) -> Dict[str, Any]:
    """429 Too many guest generations from one source address."""
    return error_response(
        error_code="GUEST_IP_LIMIT",
        message="Too many guest generations from this network. Please sign in.",
        **kwargs,
    )


def guest_global_limit(**kwargs) -> Dict[str, Any]:
    """429 Global guest traffic limit reached."""
    return error_response(
        error_code="GUEST_GLOBAL_LIMIT",
        message="Guest traffic limit reached, please sign in",
        **kwargs,
    )


def ip_rate_limit(scope: str, **kwargs) -> Dict[str, Any]:
    """429 Too many requests to a public endpoint from one source address."""
    return error_response(
        error_code="IP_RATE_LIMIT",
        message=f"Too many {scope} requests from this network. Please try again later.",
        **kwargs,
    )


def invalid_json(**kwargs) -> Dict[str, Any]:
    """400 Invalid JSON in request body"""
    return error_response(
        error_code="INVALID_JSON",
        message="Invalid JSON in request body",
        details="The request body contains invalid JSON. Please check the format and try again.",
        **kwargs,
    )


def account_suspended(**kwargs) -> Dict[str, Any]:
    """403 Account suspended."""
    return error_response(
        error_code="ACCOUNT_SUSPENDED",
        message="Your account has been suspended. Contact support for assistance.",
        **kwargs,
    )


def model_cost_ceiling(**kwargs) -> Dict[str, Any]:
    """429 All models have reached their daily generation cap."""
    return error_response(
        error_code="MODEL_COST_CEILING",
        message="All models have reached their daily generation cap. Please try again tomorrow.",
        **kwargs,
    )


def model_disabled(model_name: str, **kwargs) -> Dict[str, Any]:
    """503 Model switched off at runtime by an operator.

    503 rather than 429: nothing the caller did caused this and no amount of
    waiting for their own window is relevant. It is the service that is
    unavailable for this model, which is what a kill switch means.
    """
    return error_response(
        error_code="MODEL_DISABLED",
        message=f"{model_name} is temporarily unavailable.",
        details="An operator has disabled this model. Try a different model.",
        model=model_name,
        **kwargs,
    )


def daily_spend_ceiling(**kwargs) -> Dict[str, Any]:
    """503 Daily spend ceiling reached — operator-side cost protection.

    The budget resets at UTC midnight, which is deterministic, so clients are
    told exactly how long to back off rather than retrying into a saturated
    ceiling.
    """
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    kwargs.setdefault("retry_after", int((tomorrow - now).total_seconds()))
    return error_response(
        error_code="DAILY_SPEND_CEILING",
        message=(
            "Service is temporarily unavailable: the daily generation budget "
            "has been reached. Please try again tomorrow."
        ),
        **kwargs,
    )


def spend_guard_degraded(**kwargs) -> Dict[str, Any]:
    """503 The cost guards cannot be evaluated and the degraded budget is spent.

    A distinct code from ``DAILY_SPEND_CEILING`` on purpose. That one means
    "the budget is known and it is exhausted"; this one means "the store that
    holds the budget is unreachable and this container has already dispatched
    all it is willing to dispatch blind". They want different operator
    responses -- raise the ceiling versus fix DynamoDB -- so they must be
    separable in the logs.

    No ``retry_after``: unlike the daily ceiling, nothing here knows when the
    store comes back, and a guessed interval is worse than silence.
    """
    return error_response(
        error_code="SPEND_GUARD_DEGRADED",
        message=(
            "Service is temporarily unavailable: usage limits cannot be "
            "verified right now. Please try again shortly."
        ),
        **kwargs,
    )


def generation_dispatch_failed(**kwargs) -> Dict[str, Any]:
    """503 Asynchronous generation was requested but the worker Invoke did not land.

    Distinct from ``INTERNAL_SERVER_ERROR`` because the cause is a deployment
    fact, not a bug in the request: the ``lambda:InvokeFunction`` grant is
    absent, or the account is throttling. Both are operator-fixable and both
    clear on their own, so the client should retry rather than treat the
    prompt as rejected.

    Returned instead of silently running the dispatch inline. Inline is the
    right fallback only when the operator chose synchronous mode; when they
    asked for async, the inline path runs a ~70s budget behind a 29s gateway
    integration timeout, so the caller gets a 504 and never learns the
    sessionId while four providers generate and bill for images nobody can
    reach.
    """
    return error_response(
        error_code="GENERATION_DISPATCH_FAILED",
        message=(
            "Service is temporarily unavailable: generation could not be "
            "queued right now. Please try again shortly."
        ),
        **kwargs,
    )


def age_verification_required(**kwargs) -> Dict[str, Any]:
    """403 Caller has not affirmed they are 18 or older.

    Also returned when the affirmation store is unreachable. Being unable to
    recall that someone answered is a reason to ask again, not a reason to
    refuse them or to wave them through.
    """
    return error_response(
        error_code="AGE_VERIFICATION_REQUIRED",
        message="You must confirm you are 18 or older to use this service.",
        **kwargs,
    )


def captcha_required(**kwargs) -> Dict[str, Any]:
    """403 CAPTCHA verification required."""
    return error_response(
        error_code="CAPTCHA_REQUIRED",
        message="CAPTCHA verification required",
        **kwargs,
    )


def captcha_failed(**kwargs) -> Dict[str, Any]:
    """403 CAPTCHA verification failed."""
    return error_response(
        error_code="CAPTCHA_FAILED",
        message="CAPTCHA verification failed. Please try again.",
        **kwargs,
    )


def admin_required(**kwargs) -> Dict[str, Any]:
    """403 Admin access required."""
    return error_response(
        error_code="ADMIN_REQUIRED",
        message="Admin access required",
        **kwargs,
    )


def admin_disabled(**kwargs) -> Dict[str, Any]:
    """501 Admin features are disabled."""
    return error_response(
        error_code="ADMIN_DISABLED",
        message="Admin features are disabled",
        **kwargs,
    )
