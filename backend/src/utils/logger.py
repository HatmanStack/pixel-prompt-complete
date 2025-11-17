"""
Structured Logging Utility for Pixel Prompt Complete.

Provides JSON-formatted logging with correlation ID support for CloudWatch Logs.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any


# Configure Python logging for CloudWatch
logger = logging.getLogger()
logger.setLevel(logging.INFO)


class StructuredLogger:
    """
    Structured logger that formats log entries as JSON for CloudWatch Logs.
    """

    @staticmethod
    def log(
        level: str,
        message: str,
        correlation_id: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Log a structured message to CloudWatch.

        Args:
            level: Log level (ERROR, WARNING, INFO, DEBUG)
            message: Log message
            correlation_id: Optional correlation ID for request tracing
            **kwargs: Additional metadata fields
        """
        # Build structured log entry
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message
        }

        # Add correlation ID if provided
        if correlation_id:
            log_entry["correlationId"] = correlation_id

        # Add any additional metadata
        if kwargs:
            log_entry["metadata"] = kwargs

        # Convert to JSON
        log_json = json.dumps(log_entry)

        # Log at appropriate level
        if level == "ERROR":
            logger.error(log_json)
        elif level == "WARNING":
            logger.warning(log_json)
        elif level == "DEBUG":
            logger.debug(log_json)
        else:  # INFO or default
            logger.info(log_json)

    @staticmethod
    def error(message: str, correlation_id: Optional[str] = None, **kwargs) -> None:
        """Log error message."""
        StructuredLogger.log("ERROR", message, correlation_id, **kwargs)

    @staticmethod
    def warning(message: str, correlation_id: Optional[str] = None, **kwargs) -> None:
        """Log warning message."""
        StructuredLogger.log("WARNING", message, correlation_id, **kwargs)

    @staticmethod
    def info(message: str, correlation_id: Optional[str] = None, **kwargs) -> None:
        """Log info message."""
        StructuredLogger.log("INFO", message, correlation_id, **kwargs)

    @staticmethod
    def debug(message: str, correlation_id: Optional[str] = None, **kwargs) -> None:
        """Log debug message."""
        StructuredLogger.log("DEBUG", message, correlation_id, **kwargs)


def log_with_correlation(
    level: str,
    message: str,
    correlation_id: Optional[str] = None,
    **kwargs
) -> None:
    """
    Convenience function for logging with correlation ID.

    Args:
        level: Log level (ERROR, WARNING, INFO, DEBUG)
        message: Log message
        correlation_id: Correlation ID for request tracing
        **kwargs: Additional metadata fields
    """
    StructuredLogger.log(level, message, correlation_id, **kwargs)
