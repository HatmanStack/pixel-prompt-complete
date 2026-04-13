"""DynamoDB-backed user repository with atomic quota updates.

Implements the ``users`` table described in Phase-0.md ADR-3 / ADR-4.
All counter updates use conditional ``UpdateItem`` calls so window reset
and increment happen atomically in a single round trip.
"""

from __future__ import annotations

import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

_GLOBAL_GUEST_KEY = "guest#__global__"
_MAX_RETRIES = 3


class UserRepository:
    """CRUD + atomic quota updates for the users table."""

    def __init__(self, table_name: str, dynamodb_resource: Any | None = None) -> None:
        self.table_name = table_name
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self._table = self._dynamodb.Table(table_name)

    # ---------- basic CRUD ----------

    def get_user(self, user_id: str) -> dict | None:
        resp = self._table.get_item(Key={"userId": user_id})
        return resp.get("Item")

    def get_or_create_user(
        self, user_id: str, email: str | None = None, now: int | None = None
    ) -> dict:
        existing = self.get_user(user_id)
        if existing:
            return existing
        if now is None:
            now = int(time.time())
        item: dict[str, Any] = {
            "userId": user_id,
            "tier": "free",
            "generateCount": 0,
            "refineCount": 0,
            "dailyCount": 0,
            "windowStart": now,
            "dailyResetAt": now,
            "createdAt": now,
            "updatedAt": now,
        }
        if email:
            item["email"] = email
        try:
            self._table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(userId)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            return self.get_user(user_id) or item
        return item

    # ---------- counter helpers ----------

    def _reset_if_stale(
        self,
        user_id: str,
        field_window: str,
        fields_to_zero: list[str],
        window_seconds: int,
        now: int,
    ) -> None:
        """Reset the given counter fields if the window start is stale."""
        update_parts = [f"{field_window} = :now", "updatedAt = :now"]
        for f in fields_to_zero:
            update_parts.append(f"{f} = :zero")
        try:
            self._table.update_item(
                Key={"userId": user_id},
                UpdateExpression="SET " + ", ".join(update_parts),
                ConditionExpression=(
                    "attribute_exists(userId) AND "
                    f"(attribute_not_exists({field_window}) OR {field_window} <= :stale)"
                ),
                ExpressionAttributeValues={
                    ":now": now,
                    ":zero": 0,
                    ":stale": now - window_seconds,
                },
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    def touch_quota_window(self, user_id: str, window_seconds: int, now: int) -> dict:
        """Ensure the user exists and reset counters if the window expired."""
        self.get_or_create_user(user_id, now=now)
        self._reset_if_stale(
            user_id,
            "windowStart",
            ["generateCount", "refineCount"],
            window_seconds,
            now,
        )
        # Also reset the daily quota window (paid users use dailyCount).
        self._reset_if_stale(
            user_id,
            "dailyResetAt",
            ["dailyCount"],
            86400,
            now,
        )
        return self.get_user(user_id) or {}

    def _atomic_increment(
        self,
        user_id: str,
        counter: str,
        window_field: str,
        window_seconds: int,
        limit: int,
        now: int,
        create_if_missing: bool = True,
    ) -> tuple[bool, dict]:
        """Atomic: reset window if stale, then increment if under limit."""
        if create_if_missing:
            self.get_or_create_user(user_id, now=now)

        # Determine sibling counters to zero on window reset.
        _SIBLING_COUNTERS = {
            ("windowStart", "generateCount"): ["generateCount", "refineCount"],
            ("windowStart", "refineCount"): ["generateCount", "refineCount"],
        }
        fields_to_zero = _SIBLING_COUNTERS.get((window_field, counter), [counter])

        for _ in range(_MAX_RETRIES):
            # Reset window if stale (no-op otherwise).
            self._reset_if_stale(user_id, window_field, fields_to_zero, window_seconds, now)
            try:
                resp = self._table.update_item(
                    Key={"userId": user_id},
                    UpdateExpression=(
                        f"SET {window_field} = if_not_exists({window_field}, :now), "
                        "updatedAt = :now "
                        f"ADD {counter} :one"
                    ),
                    ConditionExpression=(
                        f"(attribute_not_exists({counter}) OR {counter} < :limit) "
                        f"AND (attribute_not_exists({window_field}) "
                        f"OR {window_field} > :stale)"
                    ),
                    ExpressionAttributeValues={
                        ":one": 1,
                        ":limit": limit,
                        ":now": now,
                        ":stale": now - window_seconds,
                    },
                    ReturnValues="ALL_NEW",
                )
                return True, resp.get("Attributes", {})
            except ClientError as e:
                if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
                # Determine whether it failed due to limit or stale window; if
                # stale, the next loop iteration will reset. If limit, return.
                item = self.get_user(user_id) or {}
                w = item.get(window_field, 0)
                if w and int(w) > now - window_seconds:
                    # Not stale: limit hit.
                    return False, item
                # Otherwise retry after reset.
                continue
        return False, self.get_user(user_id) or {}

    def increment_generate(
        self, user_id: str, window_seconds: int, limit: int, now: int
    ) -> tuple[bool, dict]:
        return self._atomic_increment(
            user_id, "generateCount", "windowStart", window_seconds, limit, now
        )

    def increment_refine(
        self, user_id: str, window_seconds: int, limit: int, now: int
    ) -> tuple[bool, dict]:
        return self._atomic_increment(
            user_id, "refineCount", "windowStart", window_seconds, limit, now
        )

    def increment_daily(
        self, user_id: str, window_seconds: int, limit: int, now: int
    ) -> tuple[bool, dict]:
        return self._atomic_increment(
            user_id, "dailyCount", "dailyResetAt", window_seconds, limit, now
        )

    # ---------- admin scan ----------

    _NON_USER_PREFIXES = ("guest#", "model#", "metrics#", "revenue#", "config#")

    def scan_users(
        self,
        limit: int = 50,
        last_key: dict | None = None,
        tier_filter: str | None = None,
        suspended_filter: bool | None = None,
    ) -> tuple[list[dict], dict | None]:
        """Scan for real user records, excluding synthetic items.

        Returns (items, LastEvaluatedKey_or_None).
        """
        filter_parts: list[str] = []
        values: dict[str, Any] = {}

        if tier_filter:
            filter_parts.append("tier = :tier")
            values[":tier"] = tier_filter

        if suspended_filter is True:
            filter_parts.append("isSuspended = :susp")
            values[":susp"] = True
        elif suspended_filter is False:
            filter_parts.append("(attribute_not_exists(isSuspended) OR isSuspended = :susp)")
            values[":susp"] = False

        scan_kwargs: dict[str, Any] = {"Limit": limit}
        if filter_parts:
            scan_kwargs["FilterExpression"] = " AND ".join(filter_parts)
            scan_kwargs["ExpressionAttributeValues"] = values
        if last_key:
            scan_kwargs["ExclusiveStartKey"] = last_key

        # We may need multiple pages to fill `limit` items after filtering
        # synthetic records, so loop until we have enough or exhaust the table.
        collected: list[dict] = []
        out_last_key: dict | None = None

        while True:
            resp = self._table.scan(**scan_kwargs)
            for item in resp.get("Items", []):
                uid = item.get("userId", "")
                if any(uid.startswith(prefix) for prefix in self._NON_USER_PREFIXES):
                    continue
                collected.append(item)

            out_last_key = resp.get("LastEvaluatedKey")
            if len(collected) >= limit or not out_last_key:
                break
            scan_kwargs["ExclusiveStartKey"] = out_last_key

        return collected[:limit], out_last_key

    # ---------- suspension ----------

    def suspend_user(self, user_id: str) -> None:
        """Set isSuspended=true on a user record."""
        now = int(time.time())
        self._table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET isSuspended = :t, updatedAt = :now",
            ExpressionAttributeValues={":t": True, ":now": now},
        )

    def unsuspend_user(self, user_id: str) -> None:
        """Set isSuspended=false on a user record."""
        now = int(time.time())
        self._table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET isSuspended = :f, updatedAt = :now",
            ExpressionAttributeValues={":f": False, ":now": now},
        )

    def is_suspended(self, user_id: str) -> bool:
        """Return True if the user exists and is suspended."""
        item = self.get_user(user_id)
        if not item:
            return False
        return bool(item.get("isSuspended", False))

    # ---------- tier / stripe ----------

    def set_tier(self, user_id: str, tier: str, **stripe_fields: Any) -> None:
        now = int(time.time())
        parts = ["tier = :tier", "updatedAt = :now"]
        values: dict[str, Any] = {":tier": tier, ":now": now}
        for i, (k, v) in enumerate(stripe_fields.items()):
            placeholder = f":v{i}"
            parts.append(f"{k} = {placeholder}")
            values[placeholder] = v
        self._table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET " + ", ".join(parts),
            ExpressionAttributeValues=values,
        )

    def set_stripe_customer_id(self, user_id: str, customer_id: str) -> None:
        now = int(time.time())
        self._table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET stripeCustomerId = :cid, updatedAt = :now",
            ExpressionAttributeValues={":cid": customer_id, ":now": now},
        )

    # ---------- guest items ----------

    def upsert_guest(self, token_id: str, ip_hash: str, ttl: int) -> dict:
        key = f"guest#{token_id}"
        existing = self.get_user(key)
        if existing:
            return existing
        now = int(time.time())
        item = {
            "userId": key,
            "tier": "guest",
            "generateCount": 0,
            "windowStart": now,
            "ipHash": ip_hash,
            "ttl": ttl,
            "createdAt": now,
            "updatedAt": now,
        }
        try:
            self._table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(userId)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            return self.get_user(key) or item
        return item

    def increment_guest_generate(
        self, token_id: str, limit: int, window_seconds: int, now: int
    ) -> tuple[bool, dict]:
        key = f"guest#{token_id}"
        return self._atomic_increment(
            key,
            "generateCount",
            "windowStart",
            window_seconds,
            limit,
            now,
            create_if_missing=False,
        )

    # ---------- revenue counters ----------

    def increment_revenue_counter(self, field: str, delta: int) -> None:
        """Atomically increment a counter on the ``revenue#current`` item.

        Creates the item if it does not exist (DynamoDB ``ADD`` creates
        the attribute starting from zero on a missing item, and the key
        is set automatically by ``UpdateItem``).
        """
        now = int(time.time())
        self._table.update_item(
            Key={"userId": "revenue#current"},
            UpdateExpression=f"SET updatedAt = :now ADD {field} :delta",
            ExpressionAttributeValues={
                ":now": now,
                ":delta": delta,
            },
        )

    def decrement_revenue_counter(self, field: str, delta: int) -> None:
        """Atomically decrement a counter (increment by negative delta)."""
        self.increment_revenue_counter(field, -delta)

    def get_revenue(self) -> dict:
        """Return the ``revenue#current`` item, or empty dict if none."""
        return self.get_user("revenue#current") or {}

    def increment_global_guest(
        self, limit: int, window_seconds: int, now: int
    ) -> tuple[bool, dict]:
        # Ensure the global item exists.
        try:
            self._table.put_item(
                Item={
                    "userId": _GLOBAL_GUEST_KEY,
                    "tier": "guest",
                    "generateCount": 0,
                    "windowStart": now,
                    "createdAt": now,
                    "updatedAt": now,
                },
                ConditionExpression="attribute_not_exists(userId)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
        return self._atomic_increment(
            _GLOBAL_GUEST_KEY,
            "generateCount",
            "windowStart",
            window_seconds,
            limit,
            now,
            create_if_missing=False,
        )
