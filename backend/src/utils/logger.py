"""
Structured Logging Utility for Pixel Prompt Complete.

Provides JSON-formatted logging with correlation ID support for CloudWatch Logs.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

# A NAMED logger, not the root one.
#
# This used to be `logging.getLogger()` at INFO, which is the root logger.
# botocore, urllib3, the OpenAI SDK and google-genai all propagate to root and
# set no level of their own, so every one of their INFO records was emitted to
# CloudWatch on every invocation -- ingestion cost and 30-day retention, for
# records nobody reads.
#
# The mechanism is easy to get backwards, so: a record's level is checked
# against the EMITTING logger's effective level, and the record is then handed
# to every ancestor's handlers regardless of those ancestors' levels. So this
# logger at INFO still reaches the handler the Lambda runtime installs on
# root, while root at WARNING silences the SDK loggers that inherit from it.
# Both halves are load-bearing; tests/backend/unit/test_logger_levels.py
# asserts each rather than trusting the reasoning.
logger = logging.getLogger("pixel_prompt")
logger.setLevel(logging.INFO)

# Set explicitly rather than left alone: the runtime's default root level has
# varied across Lambda Python runtimes, and "whatever the platform happens to
# do" is not a policy anyone can review.
logging.getLogger().setLevel(logging.WARNING)


class StructuredLogger:
    """
    Structured logger that formats log entries as JSON for CloudWatch Logs.
    """

    @staticmethod
    def log(level: str, message: str, correlation_id: Optional[str] = None, **kwargs) -> None:
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
            "message": message,
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
