"""CloudWatch custom metrics and daily snapshot handler.

Emits per-request operational metrics (request count, error count, latency)
to CloudWatch namespace ``PixelPrompt/Operations``.  The daily snapshot
handler is added in Task 6.
"""

from __future__ import annotations

import boto3

from utils.logger import StructuredLogger

_CW_NAMESPACE = "PixelPrompt/Operations"

# Lazily initialized CloudWatch client
_cw_client = None


def _get_cw_client():
    """Return a lazily-initialized CloudWatch client."""
    global _cw_client
    if _cw_client is None:
        _cw_client = boto3.client("cloudwatch")
    return _cw_client


def emit_request_metric(
    endpoint: str,
    model: str | None,
    duration_ms: float,
    is_error: bool,
) -> None:
    """Emit per-request metrics to CloudWatch. Fire-and-forget.

    Args:
        endpoint: API endpoint path (e.g. ``/generate``, ``/iterate``).
        model: Model name if applicable, or None.
        duration_ms: Request duration in milliseconds.
        is_error: Whether the request resulted in an error.
    """
    try:
        dimensions = [{"Name": "Endpoint", "Value": endpoint}]
        if model is not None:
            dimensions.append({"Name": "Model", "Value": model})

        metric_data = [
            {
                "MetricName": "RequestCount",
                "Value": 1,
                "Unit": "Count",
                "Dimensions": dimensions,
            },
            {
                "MetricName": "ErrorCount",
                "Value": 1 if is_error else 0,
                "Unit": "Count",
                "Dimensions": dimensions,
            },
            {
                "MetricName": "Latency",
                "Value": duration_ms,
                "Unit": "Milliseconds",
                "Dimensions": dimensions,
            },
        ]

        client = _get_cw_client()
        client.put_metric_data(Namespace=_CW_NAMESPACE, MetricData=metric_data)
    except Exception as e:
        StructuredLogger.error(f"Failed to emit CloudWatch metric: {e}")
