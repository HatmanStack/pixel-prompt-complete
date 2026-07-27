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
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

import config
from users.repository import UserRepository
from utils.http import invocation_ack
from utils.logger import StructuredLogger

_CW_NAMESPACE = "PixelPrompt/Operations"

# Lazily initialized CloudWatch client
_cw_client = None


# put_metric_data is a synchronous network call on the request path. The
# handlers catch its exceptions, which makes telemetry failure-safe but not
# latency-safe: with botocore's defaults (60s connect and read, legacy
# retries) a degraded CloudWatch could add minutes to a user's request while
# still "succeeding".
#
# Backgrounding is not an option here. Lambda freezes the execution
# environment once the response is returned, so a thread that has not flushed
# is simply lost — and may then resume mid-write on the next invocation.
# Bounding the call is the correct fix for this runtime.
_CW_TIMEOUT_SECONDS = 2
_CW_MAX_ATTEMPTS = 2

# PutMetricData accepts at most 1,000 datums per request.
_CW_MAX_DATUMS_PER_CALL = 1000


def _get_cw_client() -> Any:
    """Return a lazily-initialized CloudWatch client with bounded timeouts."""
    global _cw_client
    if _cw_client is None:
        _cw_client = boto3.client(
            "cloudwatch",
            config=BotoConfig(
                connect_timeout=_CW_TIMEOUT_SECONDS,
                read_timeout=_CW_TIMEOUT_SECONDS,
                retries={"mode": "standard", "total_max_attempts": _CW_MAX_ATTEMPTS},
            ),
        )
    return _cw_client


def _request_datums(
    endpoint: str,
    model: str | None,
    duration_ms: float,
    is_error: bool,
) -> list[dict[str, Any]]:
    """The four datums one request contributes."""
    dimensions = [{"Name": "Endpoint", "Value": endpoint}]
    if model is not None:
        dimensions.append({"Name": "Model", "Value": model})

    return [
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
        # Undimensioned copy. A CloudWatch alarm cannot sum across
        # dimension values, so an alarm on "errors across all providers"
        # has no series to match unless one is published without
        # dimensions. Same requirement as TotalSpendUsd and
        # TotalQuotaRejections.
        {
            "MetricName": "TotalErrorCount",
            "Value": 1 if is_error else 0,
            "Unit": "Count",
        },
    ]


def emit_request_metrics(entries: list[tuple[str, str | None, float, bool]]) -> None:
    """Emit per-request metrics for several requests at once. Fire-and-forget.

    ``/generate`` dispatches four models and used to call ``put_metric_data``
    once per model. Each call is bounded at 2s connect + 2s read x 2 attempts,
    so four models could add up to ~16 seconds of blocking network time to
    publish sixteen datums that ``PutMetricData`` accepts in a single request.

    Args:
        entries: ``(endpoint, model, duration_ms, is_error)`` per request.
    """
    if not entries:
        return
    try:
        metric_data: list[dict[str, Any]] = []
        for endpoint, model, duration_ms, is_error in entries:
            metric_data.extend(_request_datums(endpoint, model, duration_ms, is_error))

        client = _get_cw_client()
        # Four models produce sixteen datums and cannot approach the limit.
        # Chunking anyway: a loop that is correct for any input is shorter to
        # reason about than one that is correct for four.
        for start in range(0, len(metric_data), _CW_MAX_DATUMS_PER_CALL):
            client.put_metric_data(
                Namespace=_CW_NAMESPACE,
                MetricData=metric_data[start : start + _CW_MAX_DATUMS_PER_CALL],
            )
    except Exception as e:
        StructuredLogger.error(f"Failed to emit CloudWatch metric: {e}")


def emit_request_metric(
    endpoint: str,
    model: str | None,
    duration_ms: float,
    is_error: bool,
) -> None:
    """Emit per-request metrics to CloudWatch. Fire-and-forget.

    Kept because ``_handle_refinement`` legitimately has exactly one request
    to report. Implemented as a one-element batch so there is a single code
    path and the two cannot drift.

    Args:
        endpoint: API endpoint path (e.g. ``/generate``, ``/iterate``).
        model: Model name if applicable, or None.
        duration_ms: Request duration in milliseconds.
        is_error: Whether the request resulted in an error.
    """
    emit_request_metrics([(endpoint, model, duration_ms, is_error)])


def emit_spend_metric(usd_micros: int, tier: str) -> None:
    """Emit request spend to CloudWatch, in dollars. Fire-and-forget.

    The ledger records micro-dollars because DynamoDB counters must be
    integers, but this emits dollars: an alarm threshold a human sets should
    read "50", not "50000000". CloudWatch metrics are not accumulators, so
    the float carries no drift risk here.

    Spend lives in DynamoDB and is visible on the admin dashboard, but
    neither of those can page anyone. This is what makes a runaway bill
    something that wakes an operator rather than something discovered on the
    next invoice.
    """
    if usd_micros <= 0:
        return
    try:
        client = _get_cw_client()
        client.put_metric_data(
            Namespace=_CW_NAMESPACE,
            MetricData=[
                {
                    "MetricName": "SpendUsd",
                    "Value": usd_micros / 1_000_000,
                    "Unit": "None",
                    "Dimensions": [{"Name": "Tier", "Value": tier}],
                },
                # Undimensioned copy: an alarm on total spend cannot sum
                # across dimension values, so it needs its own series.
                {
                    "MetricName": "TotalSpendUsd",
                    "Value": usd_micros / 1_000_000,
                    "Unit": "None",
                },
            ],
        )
    except Exception as e:
        StructuredLogger.error(f"Failed to emit spend metric: {e}")


def emit_quota_rejection(tier: str, endpoint: str, reason: str) -> None:
    """Emit a quota/limit rejection. Fire-and-forget.

    Rejections were invisible: a user hitting a wall and an attacker probing
    one looked identical from outside, and a limit set wrongly low produced
    silent churn rather than a signal.
    """
    try:
        client = _get_cw_client()
        client.put_metric_data(
            Namespace=_CW_NAMESPACE,
            MetricData=[
                {
                    "MetricName": "QuotaRejection",
                    "Value": 1,
                    "Unit": "Count",
                    "Dimensions": [
                        {"Name": "Tier", "Value": tier},
                        {"Name": "Endpoint", "Value": endpoint},
                        {"Name": "Reason", "Value": reason},
                    ],
                },
                {"MetricName": "TotalQuotaRejections", "Value": 1, "Unit": "Count"},
            ],
        )
    except Exception as e:
        StructuredLogger.error(f"Failed to emit quota rejection metric: {e}")


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

    # 5. Repair the monthly spend accumulator from the daily items.
    #    It is a cache written alongside each daily write, so a partial
    #    failure leaves it under-counting, and under-counting means the
    #    ceiling that caps the invoice trips later than it should.
    try:
        from ops.cost_meter import reconcile_monthly_spend

        reconcile_monthly_spend(repo, now)
    except Exception as e:
        StructuredLogger.error(f"Monthly spend reconciliation failed: {e}")

    # 6. Reset monthly churn on first of month
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
    return invocation_ack(f"Snapshot {today} complete")
