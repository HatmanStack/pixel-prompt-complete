"""DynamoDB-backed user repository with atomic quota updates.

Implements the single-table design in docs/adr/003-dynamodb-single-table.md.
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
# How long a processed Stripe event id is remembered for dedup. Stripe retries
# a failing webhook for up to 3 days; 30 days is a comfortable margin.
_WEBHOOK_EVENT_TTL_SECONDS = 30 * 86400
# How long a single delivery may hold the claim before another delivery may
# reclaim it. Bounds the damage when release-on-failure itself fails: without
# a lease the claim would persist and every Stripe retry would be answered
# "duplicate", silently losing the event.
_WEBHOOK_LEASE_SECONDS = 900
# Grace added to a per-IP counter's window before it may be reaped. DynamoDB
# TTL deletion is lazy (up to ~48h), so the bucket must comfortably outlive
# the window it is counting or a live counter could vanish mid-window.
_IP_BUCKET_TTL_GRACE_SECONDS = 3 * 86400


class UserRepository:
    """CRUD + atomic quota updates for the users table."""

    def __init__(self, table_name: str, dynamodb_resource: Any | None = None) -> None:
        self.table_name = table_name
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self._table = self._dynamodb.Table(table_name)

    # ---------- basic CRUD ----------

    def get_user(self, user_id: str) -> dict | None:
        resp = self._table.get_item(Key={"userId": user_id})
        # boto3 is untyped, so resp is Any. Annotate rather than let an
        # implicit Any satisfy the declared return type.
        item: dict | None = resp.get("Item")
        return item

    def get_or_create_user(
        self,
        user_id: str,
        email: str | None = None,
        now: int | None = None,
        ttl: int | None = None,
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
        if ttl is not None:
            # Only ever set for ephemeral counter buckets. Real user records
            # must never carry a TTL — expiring one would delete a customer.
            item["ttl"] = ttl
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
        # Also reset the daily quota window. Paid users have two counters on
        # this one window — refinement and generation — and both must be
        # zeroed together, or GET /me reports a count the quota layer has
        # already forgotten.
        self._reset_if_stale(
            user_id,
            "dailyResetAt",
            ["dailyCount", "dailyGenerateCount"],
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
        ttl: int | None = None,
    ) -> tuple[bool, dict]:
        """Atomic: reset window if stale, then increment if under limit.

        ``ttl`` is for ephemeral buckets (per-IP abuse counters) only. Leave it
        None for real user records.
        """
        if create_if_missing:
            self.get_or_create_user(user_id, now=now, ttl=ttl)

        # Determine sibling counters to zero on window reset. Every counter
        # sharing a window field must appear in the other's entry: zeroing one
        # and not the other leaves the sibling stranded at its limit for as
        # long as the account keeps the window alive.
        _SIBLING_COUNTERS = {
            ("windowStart", "generateCount"): ["generateCount", "refineCount"],
            ("windowStart", "refineCount"): ["generateCount", "refineCount"],
            ("dailyResetAt", "dailyCount"): ["dailyCount", "dailyGenerateCount"],
            ("dailyResetAt", "dailyGenerateCount"): ["dailyCount", "dailyGenerateCount"],
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

    def decrement_counter(
        self,
        user_id: str,
        counter: str,
        window_field: str,
        window_seconds: int,
        now: int,
    ) -> bool:
        """Give one unit of a rolling-window counter back.

        The counterpart to :meth:`_atomic_increment`, for a request that
        consumed quota and produced nothing. Returns ``True`` when a unit was
        actually returned, ``False`` when there was nothing to return.

        A SINGLE conditional UpdateItem, and both halves of the condition are
        load-bearing:

        * ``{counter} > 0`` — a counter that is already at zero has nothing to
          give back, and ``ADD -1`` would drive it negative, which reads as
          extra allowance on the next check.
        * ``{window_field} > now - window_seconds`` — **this is the one that
          matters.** A window that has already rolled over has handed the
          caller a fresh allowance; taking a unit off the new window's counter
          would be a free extra call stacked on top of it. Refunding is meant
          to make someone whole for the window they lost it in, not to credit
          them in a window they never spent it in.

        ``ConditionalCheckFailedException`` covers both cases plus "no such
        record", and all three mean the same thing here — nothing to refund —
        so it is reported, not raised. Any other ``ClientError`` (throttling,
        access denial) propagates: that is a store failure, not an empty
        counter, and the caller logs it.
        """
        try:
            self._table.update_item(
                Key={"userId": user_id},
                UpdateExpression=f"SET updatedAt = :now ADD {counter} :minus_one",
                ConditionExpression=(f"{counter} > :zero AND {window_field} > :stale"),
                ExpressionAttributeValues={
                    ":minus_one": -1,
                    ":zero": 0,
                    ":now": now,
                    ":stale": now - window_seconds,
                },
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            return False

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

    def increment_daily_generate(
        self, user_id: str, window_seconds: int, limit: int, now: int
    ) -> tuple[bool, dict]:
        """Count a paid generation against its own daily bucket.

        Separate from ``dailyCount`` on purpose: a generation runs four
        providers and a refinement runs one, and they are priced apart
        everywhere else in this codebase. Sharing a counter would make them
        cost the same. They share ``dailyResetAt`` so the two reset together —
        see ``_SIBLING_COUNTERS``.
        """
        return self._atomic_increment(
            user_id, "dailyGenerateCount", "dailyResetAt", window_seconds, limit, now
        )

    # ---------- admin scan ----------

    _NON_USER_PREFIXES = (
        "guest#",
        "model#",
        "metrics#",
        "revenue#",
        "config#",
        "event#",
        "prompt#",
        "spend#",
        "anon#",
    )

    def scan_users(
        self,
        limit: int = 50,
        last_key: dict | None = None,
        tier_filter: str | None = None,
        suspended_filter: bool | None = None,
        max_pages: int = 5,
    ) -> tuple[list[dict], dict | None]:
        """Scan for real user records, excluding synthetic items.

        Returns ``(items, cursor_or_None)``. The cursor is an
        ``ExclusiveStartKey`` for the next call.

        **The cursor keys off the last item RETURNED, not the last page
        scanned.** It used to return ``collected[:limit]`` paired with the
        ``LastEvaluatedKey`` of the page whose surplus items had just been
        dropped -- so feeding that key back resumed *after* the items that were
        discarded, and they reached no caller at all. The table's key schema is
        a single ``userId`` hash (backend/template.yaml), so the key of any
        item is a complete and valid ``ExclusiveStartKey``.

        ``max_pages`` is a COST bound, not a correctness bound. Synthetic
        records (``guest#``, ``spend#``, ``anon#``, ...) are filtered
        client-side and vastly outnumber real users on a live table, so a
        request for one page of users could otherwise scan the whole thing.
        Hitting the ceiling returns a short page with the scan's own
        ``LastEvaluatedKey``; a short page is a normal DynamoDB result and the
        admin UI already pages.
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
        # synthetic records, so loop until we have enough, exhaust the table,
        # or hit the page ceiling.
        collected: list[dict] = []
        page_last_key: dict | None = None

        for _ in range(max_pages):
            resp = self._table.scan(**scan_kwargs)
            for item in resp.get("Items", []):
                uid = item.get("userId", "")
                if any(uid.startswith(prefix) for prefix in self._NON_USER_PREFIXES):
                    continue
                collected.append(item)

            page_last_key = resp.get("LastEvaluatedKey")
            if len(collected) >= limit or not page_last_key:
                break
            scan_kwargs["ExclusiveStartKey"] = page_last_key

        if len(collected) >= limit:
            page = collected[:limit]
            # Resume from the last item the caller actually receives, so the
            # surplus this truncation drops is returned next time rather than
            # skipped.
            return page, {"userId": page[-1]["userId"]}

        # Under the limit: either the table is exhausted (no key) or the page
        # ceiling stopped us early (key present, short page).
        return collected, page_last_key

    # ---------- model runtime config ----------

    def get_model_runtime_config(self, model_name: str) -> dict | None:
        """Get the runtime config item for a model (``config#model#<name>``)."""
        return self.get_user(f"config#model#{model_name}")

    def set_model_runtime_config(self, model_name: str, disabled: bool) -> None:
        """Set or update the runtime config for a model."""
        now = int(time.time())
        self._table.update_item(
            Key={"userId": f"config#model#{model_name}"},
            UpdateExpression="SET disabled = :d, updatedAt = :now",
            ExpressionAttributeValues={":d": disabled, ":now": now},
        )

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

    def get_user_by_stripe_customer_id(self, customer_id: str) -> dict | None:
        """Reverse-lookup a user from their Stripe customer id.

        Backs the webhook resolver's last-resort path: real
        ``customer.subscription.*`` payloads carry no ``client_reference_id``
        and, for subscriptions created before ``subscription_data.metadata``
        was set at checkout, no ``metadata.userId`` either. The customer id
        is the only identifier such an event always carries.

        The index is ``KEYS_ONLY``, so this costs one query plus one
        ``GetItem`` to hydrate the full record.
        """
        if not customer_id:
            return None
        response = self._table.query(
            IndexName="StripeCustomerIndex",
            KeyConditionExpression="stripeCustomerId = :cid",
            ExpressionAttributeValues={":cid": customer_id},
            Limit=1,
        )
        items = response.get("Items") or []
        if not items:
            return None
        return self.get_user(items[0]["userId"])

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

    def has_affirmed_age(self, identity_key: str) -> bool:
        """Return True if this identity has previously affirmed being 18+.

        ``identity_key`` is ``TierContext.user_id``, which already namespaces
        guests (``guest#...``) and anonymous callers (``anon#...``) apart from
        Cognito subs, so one method covers every tier.
        """
        item = self.get_user(identity_key)
        return bool(item and item.get("ageAffirmedAt"))

    def record_age_affirmation(
        self, identity_key: str, now: int, ephemeral_window_seconds: int | None = None
    ) -> None:
        """Record that this identity affirmed being 18+.

        The record is initialised first rather than being conjured by this
        write. A bare item created here would satisfy ``get_or_create_user``'s
        existence check on a later call, so the quota path would skip
        initialisation and the row would keep whatever TTL this method chose
        instead of the one its counter bucket expects. For an anonymous caller
        that meant an abuse counter living 24x longer than its own window.

        ``ephemeral_window_seconds`` is the caller's quota window for guest and
        anonymous identities, so the TTL matches what ``increment_anon`` and
        friends would have set. Pass None for real accounts: a TTL on one of
        those would delete a customer.

        The affirmation itself is written only if absent, so the timestamp is
        the first affirmation rather than the most recent request, and an
        existing record's TTL is never touched.
        """
        if ephemeral_window_seconds is not None:
            self.get_or_create_user(
                identity_key,
                now=now,
                ttl=now + ephemeral_window_seconds + _IP_BUCKET_TTL_GRACE_SECONDS,
            )
        else:
            self.get_or_create_user(identity_key, now=now)

        try:
            self._table.update_item(
                Key={"userId": identity_key},
                UpdateExpression="SET ageAffirmedAt = :now, updatedAt = :now",
                ConditionExpression="attribute_not_exists(ageAffirmedAt)",
                ExpressionAttributeValues={":now": now},
            )
        except ClientError as e:
            # Already affirmed. Two concurrent first requests race here and the
            # loser is not an error: the fact we wanted recorded is recorded.
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    def increment_anon(
        self, key: str, counter: str, limit: int, window_seconds: int, now: int
    ) -> tuple[bool, dict]:
        """Count unauthenticated requests per source-IP bucket.

        Expires: one row per unique caller IP, kept forever, would be
        unbounded storage growth on a public deployment — an abuse counter
        that outlives its own window is just litter.
        """
        return self._atomic_increment(
            key,
            counter,
            "windowStart",
            window_seconds,
            limit,
            now,
            create_if_missing=True,
            ttl=now + window_seconds + _IP_BUCKET_TTL_GRACE_SECONDS,
        )

    def increment_guest_ip(
        self, ip_hash: str, limit: int, window_seconds: int, now: int
    ) -> tuple[bool, dict]:
        """Count guest generates per source-IP hash.

        The per-token counter is trivially reset by discarding a cookie, so it
        bounds nothing. This one is keyed on something the caller does not
        choose, which is what makes it an actual limit.

        The ``ipHash`` this reads was already being computed and stored on
        every guest record — it was simply never used for anything.
        """
        key = f"guest#ip#{ip_hash}"
        return self._atomic_increment(
            key,
            "generateCount",
            "windowStart",
            window_seconds,
            limit,
            now,
            create_if_missing=True,
            ttl=now + window_seconds + _IP_BUCKET_TTL_GRACE_SECONDS,
        )

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

    # ---------- model preference ----------

    def record_model_choice(self, user_id: str, model_name: str, now: int | None = None) -> None:
        """Count that this user chose ``model_name`` to refine.

        Generating produces four images the user did not choose between.
        Refining one is the first moment they express a preference, and it is
        a stronger signal than a click or a download because it costs them
        something.

        Stored per user as ``modelChoice<Model>`` counters so the answer to
        "which model wins for this person" is a single item read rather than
        a scan over session history. Best-effort at the call site: this is
        product data, not billing, and it must never fail a refinement.
        """
        if not user_id or user_id == "anon" or not model_name:
            return
        field = f"modelChoice{model_name.capitalize()}"
        self.add_counters(user_id, {field: 1}, now=now)

    def get_model_choices(self, user_id: str) -> dict[str, int]:
        """Per-model refinement counts for a user, highest first."""
        item = self.get_user(user_id) or {}
        choices = {
            k[len("modelChoice") :].lower(): int(v)
            for k, v in item.items()
            if k.startswith("modelChoice")
        }
        return dict(sorted(choices.items(), key=lambda kv: kv[1], reverse=True))

    # ---------- credit ledger ----------

    def debit_credits(
        self,
        user_id: str,
        amount: int,
        allotment: int,
        period_end: int,
        now: int,
    ) -> tuple[bool, dict]:
        """Debit ``amount``, granting a fresh allotment first if the period lapsed.

        Returns ``(True, item)`` on success, ``(False, item)`` when the balance
        is insufficient.

        Both outcomes are produced by a SINGLE conditional UpdateItem, never by
        a reset followed by a debit. Two atomic writes do not compose into an
        atomic unit: with a separate reset, a grant landing between another
        request's check and its write can overwrite a debit (handing out more
        than one allotment) or restore a balance that was already spent
        (driving it negative). Both were observed under concurrent load.

        * Renewal path — grants and debits together, conditioned on the period
          having lapsed. Exactly one caller can win this, because the same
          write moves ``creditPeriodEnd`` into the future.
        * Steady-state path — debits, conditioned on the period being current
          AND the balance sufficing.
        """
        if amount <= 0:
            self.get_or_create_user(user_id, now=now)
            return True, self.get_user(user_id) or {}
        if amount > allotment:
            # Could never be afforded even with a full allotment; denying is
            # correct and avoids a renewal write that would land negative.
            return False, self.get_or_create_user(user_id, now=now)

        self.get_or_create_user(user_id, now=now)

        for _ in range(_MAX_RETRIES):
            # Renewal: grant and charge in one write.
            try:
                resp = self._table.update_item(
                    Key={"userId": user_id},
                    UpdateExpression=(
                        "SET creditsRemaining = :granted, "
                        "creditPeriodEnd = :period_end, updatedAt = :now"
                    ),
                    ConditionExpression=(
                        "attribute_exists(userId) AND "
                        "(attribute_not_exists(creditPeriodEnd) OR creditPeriodEnd <= :now)"
                    ),
                    ExpressionAttributeValues={
                        ":granted": allotment - amount,
                        ":period_end": period_end,
                        ":now": now,
                    },
                    ReturnValues="ALL_NEW",
                )
                return True, resp.get("Attributes", {})
            except ClientError as e:
                if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise

            # Steady state: period is current, so charge against the balance.
            try:
                resp = self._table.update_item(
                    Key={"userId": user_id},
                    UpdateExpression=(
                        "SET creditsRemaining = creditsRemaining - :amt, updatedAt = :now"
                    ),
                    ConditionExpression=(
                        "attribute_exists(creditsRemaining) AND "
                        "creditsRemaining >= :amt AND creditPeriodEnd > :now"
                    ),
                    ExpressionAttributeValues={":amt": amount, ":now": now},
                    ReturnValues="ALL_NEW",
                )
                return True, resp.get("Attributes", {})
            except ClientError as e:
                if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
                item = self.get_user(user_id) or {}
                period = int(item.get("creditPeriodEnd", 0) or 0)
                balance = int(item.get("creditsRemaining", 0) or 0)
                if period > now and balance < amount:
                    return False, item
                # The period lapsed between the two attempts; go round again.
                continue
        return False, self.get_user(user_id) or {}

    def get_credit_balance(self, user_id: str) -> dict:
        """Read-only view of a user's ledger state."""
        item = self.get_user(user_id) or {}
        return {
            "creditsRemaining": int(item.get("creditsRemaining", 0) or 0),
            "creditPeriodEnd": int(item.get("creditPeriodEnd", 0) or 0),
        }

    def grant_credits(
        self,
        user_id: str,
        amount: int,
        now: int | None = None,
        period_end: int | None = None,
    ) -> None:
        """Add credits outside the normal period grant (top-ups, goodwill).

        **Top-ups are period-scoped.** The renewal path SETs the balance to a
        fresh allotment rather than adding to it, so anything granted here is
        replaced when the period rolls over — consistent with allotments not
        rolling over. A top-up meant to outlive the period has to be granted
        again, or the renewal semantics changed deliberately.

        ``period_end`` opens a period for a user who has none. Without it, a
        grant to such a user is wiped by their very next request, because that
        request takes the renewal path and overwrites the balance. Callers
        topping up a dormant account should pass it.
        """
        if amount <= 0:
            return
        if now is None:
            now = int(time.time())
        self.add_counters(user_id, {"creditsRemaining": amount}, now=now)
        if period_end is None:
            return
        try:
            self._table.update_item(
                Key={"userId": user_id},
                UpdateExpression="SET creditPeriodEnd = :period_end, updatedAt = :now",
                ConditionExpression=(
                    "attribute_not_exists(creditPeriodEnd) OR creditPeriodEnd <= :now"
                ),
                ExpressionAttributeValues={":period_end": period_end, ":now": now},
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    # ---------- webhook idempotency ----------

    def claim_webhook_event(self, event_id: str, now: int | None = None) -> bool:
        """Atomically claim a Stripe event id before processing it.

        Stripe guarantees at-least-once delivery, so the same event id can
        arrive repeatedly. Handlers mutate revenue counters, so replaying an
        event double-counts subscribers (and can drive ``activeSubscribers``
        negative via the cancellation path).

        Returns True if this caller won the claim and should process the
        event, False if it was already processed.
        """
        if not event_id:
            # No id to dedupe on: process rather than silently drop.
            return True
        if now is None:
            now = int(time.time())
        try:
            self._table.put_item(
                Item={
                    "userId": f"event#{event_id}",
                    "claimedAt": now,
                    "leaseExpiresAt": now + _WEBHOOK_LEASE_SECONDS,
                    "ttl": now + _WEBHOOK_EVENT_TTL_SECONDS,
                },
                ConditionExpression=(
                    "attribute_not_exists(userId) OR "
                    "(attribute_not_exists(completedAt) AND leaseExpiresAt < :now)"
                ),
                ExpressionAttributeValues={":now": now},
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return True

    def complete_webhook_event(self, event_id: str, now: int | None = None) -> None:
        """Mark an event fully processed so retries are suppressed for the TTL.

        Only a completed record blocks redelivery. An in-flight claim merely
        holds a lease, so a delivery that dies without completing (or whose
        release fails) is retried once the lease lapses rather than being
        swallowed forever.
        """
        if not event_id:
            return
        if now is None:
            now = int(time.time())
        self._table.update_item(
            Key={"userId": f"event#{event_id}"},
            UpdateExpression=("SET completedAt = :now, #ttl = :ttl REMOVE leaseExpiresAt"),
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={
                ":now": now,
                ":ttl": now + _WEBHOOK_EVENT_TTL_SECONDS,
            },
        )

    def release_webhook_event(self, event_id: str) -> None:
        """Drop a claim so Stripe's retry can re-process the event.

        Called when the handler raised after the claim was taken. Without
        this, a single transient failure would permanently swallow the
        event — which for a cancellation means a churned user keeps paid
        access forever.
        """
        if not event_id:
            return
        self._table.delete_item(Key={"userId": f"event#{event_id}"})

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

    def add_counters(
        self,
        item_key: str,
        deltas: dict[str, int],
        now: int | None = None,
        ttl: int | None = None,
    ) -> None:
        """Atomically apply several integer deltas to one item.

        A single UpdateItem applies every delta or none of them. Sequential
        calls are NOT equivalent: a failure between them can leave a caller
        half-applied, and any retry then double-counts whatever already
        landed. That is exactly how ``activeSubscribers`` went negative.
        """
        if not deltas:
            return
        if now is None:
            now = int(time.time())
        add_parts: list[str] = []
        values: dict[str, Any] = {":now": now}
        names: dict[str, str] = {}
        for i, (field, delta) in enumerate(deltas.items()):
            placeholder = f":d{i}"
            # Alias every name: cost labels are provider-derived and could
            # collide with DynamoDB reserved words.
            alias = f"#f{i}"
            names[alias] = field
            add_parts.append(f"{alias} {placeholder}")
            values[placeholder] = delta
        set_parts = ["updatedAt = :now"]
        if ttl is not None:
            # if_not_exists so the expiry is anchored to first write and a
            # long-lived accumulator cannot keep pushing its own deletion out.
            names["#ttl"] = "ttl"
            values[":ttl"] = ttl
            set_parts.append("#ttl = if_not_exists(#ttl, :ttl)")
        self._table.update_item(
            Key={"userId": item_key},
            UpdateExpression=("SET " + ", ".join(set_parts) + " ADD " + ", ".join(add_parts)),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )

    def apply_revenue_deltas(self, deltas: dict[str, int]) -> None:
        """Atomically apply several revenue counter deltas in one UpdateItem.

        All revenue counters live on the single ``revenue#current`` item.
        """
        self.add_counters("revenue#current", deltas)

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
