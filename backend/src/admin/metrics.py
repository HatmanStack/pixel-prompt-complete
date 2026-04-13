"""Admin metrics and revenue endpoints.

Handles:
- ``GET /admin/metrics`` - today's model counts and daily snapshot history
- ``GET /admin/revenue`` - current revenue counters and historical data
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from admin.auth import require_admin_request
from ops.model_counters import ModelCounterService
from users.repository import UserRepository


def _decimal_default(obj: Any) -> Any:
    """JSON encoder for DynamoDB Decimal values."""
    if isinstance(obj, Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    return str(obj)


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Build an API Gateway response."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_decimal_default),
    }


def handle_admin_metrics(
    event: dict[str, Any],
    repo: UserRepository,
    model_counter_service: ModelCounterService,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """GET /admin/metrics - today's model counts and daily snapshot history."""
    claims, err = require_admin_request(event)
    if err:
        return err

    params = event.get("queryStringParameters") or {}
    days = min(int(params.get("days", "7")), 30)

    now = int(time.time())
    today_counts = model_counter_service.get_model_counts(now)

    # Read daily snapshots for the requested range
    today = datetime.now(timezone.utc)
    history = []
    for i in range(1, days + 1):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        snapshot = repo.get_user(f"metrics#{date_str}")
        if snapshot:
            # Strip the DynamoDB key, keep just the metrics data
            history.append(
                {
                    "date": date_str,
                    "modelCounts": snapshot.get("modelCounts", {}),
                    "usersByTier": snapshot.get("usersByTier", {}),
                    "suspendedCount": int(snapshot.get("suspendedCount", 0)),
                    "revenue": snapshot.get("revenue", {}),
                }
            )

    return _response(
        200,
        {
            "today": today_counts,
            "history": history,
            "days": days,
        },
    )


def handle_admin_revenue(
    event: dict[str, Any],
    repo: UserRepository,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """GET /admin/revenue - current revenue counters and historical data."""
    claims, err = require_admin_request(event)
    if err:
        return err

    current = repo.get_revenue()
    # Strip DynamoDB metadata from the revenue item
    if current:
        current = {k: v for k, v in current.items() if k not in ("userId", "updatedAt")}

    # Read revenue history from daily snapshots
    params = event.get("queryStringParameters") or {}
    days = min(int(params.get("days", "30")), 90)

    today = datetime.now(timezone.utc)
    history = []
    for i in range(1, days + 1):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        snapshot = repo.get_user(f"metrics#{date_str}")
        if snapshot and snapshot.get("revenue"):
            history.append(
                {
                    "date": date_str,
                    "revenue": snapshot["revenue"],
                }
            )

    return _response(
        200,
        {
            "current": current,
            "history": history,
        },
    )
