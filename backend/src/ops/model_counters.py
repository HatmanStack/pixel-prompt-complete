"""Per-model daily generation counters for cost ceiling enforcement.

Uses DynamoDB items keyed as ``model#<name>`` in the existing users table,
with atomic increment via :meth:`UserRepository.increment_daily`.
"""

from __future__ import annotations

import config
from users.repository import UserRepository


class ModelCounterService:
    """Tracks per-model daily generation counts against configurable caps."""

    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    def increment_model_count(self, model_name: str, now: int) -> tuple[bool, dict]:
        """Increment the daily counter for a model.

        Returns:
            (True, item) if under cap, (False, item) if at/over cap.
        """
        cap = config.MODEL_DAILY_CAPS.get(model_name, 500)
        return self._repo.increment_daily(
            user_id=f"model#{model_name}",
            window_seconds=86400,
            limit=cap,
            now=now,
        )

    def get_model_counts(self, now: int) -> dict[str, dict]:
        """Read current daily counts for all 4 models.

        Returns:
            Dict mapping model name to {dailyCount, cap, dailyResetAt}.
        """
        result = {}
        for model_name in ("gemini", "nova", "openai", "firefly"):
            item = self._repo.get_user(f"model#{model_name}")
            cap = config.MODEL_DAILY_CAPS.get(model_name, 500)
            if item:
                result[model_name] = {
                    "dailyCount": int(item.get("dailyCount", 0)),
                    "cap": cap,
                    "dailyResetAt": int(item.get("dailyResetAt", 0)),
                }
            else:
                result[model_name] = {
                    "dailyCount": 0,
                    "cap": cap,
                    "dailyResetAt": 0,
                }
        return result

    def check_model_allowed(self, model_name: str, now: int) -> bool:
        """Convenience: returns True if model can generate, False if capped."""
        ok, _ = self.increment_model_count(model_name, now)
        return ok
