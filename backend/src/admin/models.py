"""Admin model management endpoints.

Handles:
- ``GET /admin/models`` - list all models with daily counts, caps, and status
- ``POST /admin/models/{model}/disable`` - runtime disable a model
- ``POST /admin/models/{model}/enable`` - runtime re-enable a model
"""

from __future__ import annotations

import json
from typing import Any

import config
from admin.auth import require_admin_request
from ops.model_counters import ModelCounterService
from users.repository import UserRepository


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Build an API Gateway response."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _extract_model_name(path: str) -> str:
    """Extract model name from paths like /admin/models/{model}/disable."""
    parts = path.strip("/").split("/")
    # /admin/models/{model}/... -> ["admin", "models", "{model}", ...]
    if len(parts) >= 3:
        return parts[2]
    return ""


def _validate_model_name(model_name: str) -> dict[str, Any] | None:
    """Return an error response if the model name is invalid, else None."""
    if model_name not in config.MODELS:
        valid = list(config.MODELS.keys())
        return _response(400, {"error": f"Invalid model: {model_name}. Valid: {valid}"})
    return None


def handle_admin_models_list(
    event: dict[str, Any],
    model_counter_service: ModelCounterService,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """GET /admin/models - list all models with status and counts."""
    claims, err = require_admin_request(event)
    if err:
        return err

    import time

    now = int(time.time())
    counts = model_counter_service.get_model_counts(now)

    models = []
    for name, model_cfg in config.MODELS.items():
        count_data = counts.get(name, {})
        models.append(
            {
                "name": name,
                "displayName": model_cfg.display_name,
                "enabled": model_cfg.enabled,
                "provider": model_cfg.provider,
                "dailyCount": count_data.get("dailyCount", 0),
                "dailyCap": count_data.get("cap", config.MODEL_DAILY_CAPS.get(name, 500)),
                "dailyResetAt": count_data.get("dailyResetAt", 0),
            }
        )

    return _response(200, {"models": models})


def handle_admin_model_disable(
    event: dict[str, Any],
    repo: UserRepository,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """POST /admin/models/{model}/disable - runtime disable a model."""
    claims, err = require_admin_request(event)
    if err:
        return err

    path = event.get("rawPath", "")
    model_name = _extract_model_name(path)
    err = _validate_model_name(model_name)
    if err:
        return err

    repo.set_model_runtime_config(model_name, disabled=True)

    return _response(200, {"status": "disabled", "model": model_name})


def handle_admin_model_enable(
    event: dict[str, Any],
    repo: UserRepository,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """POST /admin/models/{model}/enable - runtime re-enable a model."""
    claims, err = require_admin_request(event)
    if err:
        return err

    path = event.get("rawPath", "")
    model_name = _extract_model_name(path)
    err = _validate_model_name(model_name)
    if err:
        return err

    repo.set_model_runtime_config(model_name, disabled=False)

    return _response(200, {"status": "enabled", "model": model_name})
