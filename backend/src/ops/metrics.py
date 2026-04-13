"""CloudWatch custom metrics and daily snapshot handler.

Emits per-request operational metrics (request count, error count, latency)
to CloudWatch namespace ``PixelPrompt/Operations``.  Also contains the
``handle_daily_snapshot`` function triggered by EventBridge on a daily schedule.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

import config
from users.repository import UserRepository
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


# ---------- Daily Snapshot ----------

_MODEL_NAMES = ("gemini", "nova", "openai", "firefly")


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD in UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _is_first_of_month() -> bool:
    """Return True if today is the first day of the month (UTC)."""
    return datetime.now(timezone.utc).day == 1


def _decimal_to_int(val: Any) -> int:
    """Convert a DynamoDB Decimal to int, defaulting to 0."""
    if val is None:
        return 0
    return int(val)


def handle_daily_snapshot(
    event: dict[str, Any],
    context: Any,
    *,
    repo: UserRepository | None = None,
) -> dict[str, Any]:
    """Snapshot operational data into DynamoDB for historical tracking.

    Writes a ``metrics#YYYY-MM-DD`` item with model counts, user tier
    distribution, suspended count, and revenue.  Idempotent via
    ``attribute_not_exists`` condition.

    Args:
        repo: Optional ``UserRepository`` override (for testing).
    """
    if repo is None:
        repo = UserRepository(config.users_table_name)

    today = _today_str()
    now = int(time.time())

    # 1. Read model counters
    model_counts: dict[str, int] = {}
    for model in _MODEL_NAMES:
        item = repo.get_user(f"model#{model}")
        model_counts[model] = _decimal_to_int(item.get("dailyCount")) if item else 0

    # 2. Read revenue
    revenue_item = repo.get_revenue()
    revenue = {
        "activeSubscribers": _decimal_to_int(revenue_item.get("activeSubscribers")),
        "monthlyChurn": _decimal_to_int(revenue_item.get("monthlyChurn")),
    }

    # 3. Scan users for tier distribution and suspended count
    users_by_tier: dict[str, int] = {}
    suspended_count = 0

    table = repo._table
    scan_kwargs: dict[str, Any] = {
        "Select": "SPECIFIC_ATTRIBUTES",
        "ProjectionExpression": "userId, tier, isSuspended",
    }
    while True:
        resp = table.scan(**scan_kwargs)
        for item in resp.get("Items", []):
            uid = item.get("userId", "")
            # Skip synthetic records (model#, revenue#, metrics#, guest#)
            if "#" in uid:
                continue
            tier = item.get("tier", "unknown")
            users_by_tier[tier] = users_by_tier.get(tier, 0) + 1
            if item.get("isSuspended"):
                suspended_count += 1
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    # 4. Write snapshot (idempotent)
    try:
        table.put_item(
            Item={
                "userId": f"metrics#{today}",
                "modelCounts": model_counts,
                "usersByTier": users_by_tier,
                "suspendedCount": suspended_count,
                "revenue": revenue,
                "createdAt": now,
            },
            ConditionExpression="attribute_not_exists(userId)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            StructuredLogger.info(f"Snapshot for {today} already exists, skipping")
        else:
            raise

    # 5. Reset monthly churn on first of month
    if _is_first_of_month():
        try:
            table.update_item(
                Key={"userId": "revenue#current"},
                UpdateExpression="SET monthlyChurn = :zero, updatedAt = :now",
                ExpressionAttributeValues={":zero": 0, ":now": now},
                ConditionExpression="attribute_exists(userId)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    StructuredLogger.info(f"Daily snapshot completed for {today}")
    return {"statusCode": 200, "body": f"Snapshot {today} complete"}
