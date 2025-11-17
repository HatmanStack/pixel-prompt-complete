"""
Logging API endpoint for Pixel Prompt Complete.

Accepts frontend error logs and writes them to CloudWatch with structured format.
"""

import json
from typing import Dict, Optional
from utils.logger import StructuredLogger


# Valid log levels
VALID_LOG_LEVELS = {"ERROR", "WARNING", "INFO", "DEBUG"}


def handle_log(body: Dict, correlation_id: Optional[str] = None, ip_address: str = "unknown") -> Dict:
    """
    Handle frontend log submission.

    Args:
        body: Request body containing log data
        correlation_id: Correlation ID from request headers
        ip_address: Client IP address

    Returns:
        Dict with success status and message

    Raises:
        ValueError: If required fields are missing or invalid
    """
    # Extract required fields
    level = body.get('level', '').upper()
    message = body.get('message', '')

    # Validate required fields
    if not level:
        raise ValueError("Field 'level' is required")

    if not message:
        raise ValueError("Field 'message' is required")

    # Validate log level
    if level not in VALID_LOG_LEVELS:
        raise ValueError(f"Invalid log level '{level}'. Must be one of: {', '.join(VALID_LOG_LEVELS)}")

    # Extract optional fields
    stack = body.get('stack')
    metadata = body.get('metadata', {})

    # Add IP address to metadata
    metadata['ip'] = ip_address

    # Add stack trace to metadata if provided
    if stack:
        metadata['stack'] = stack

    # Log to CloudWatch with structured format
    StructuredLogger.log(
        level=level,
        message=message,
        correlation_id=correlation_id,
        **metadata
    )

    return {
        'success': True,
        'message': 'Log received successfully'
    }
