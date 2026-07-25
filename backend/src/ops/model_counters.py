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

    def consume_model_slot(self, model_name: str, now: int) -> bool:
        """Consume one slot against the model's daily cap.

        NOT a read-only check: this increments. Named accordingly because the
        previous name (``check_model_allowed``) read as a predicate while
        mutating, which is how the refine paths ended up never touching the
        ceiling — the call looked too cheap to matter and was simply omitted.

        Returns True if the slot was granted, False if the model is at cap.
        Use :meth:`get_model_counts` for a genuine read-only view.
        """
        ok, _ = self.increment_model_count(model_name, now)
        return ok
