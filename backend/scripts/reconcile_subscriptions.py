#!/usr/bin/env python3
"""Reconcile DynamoDB subscription state against Stripe.

Why this exists
---------------
Cancellations were silently dropped for as long as the webhook resolver
bug was live (see ``billing/webhook.py`` and
``docs/plans/2026-07-25-p0-revenue-correctness/verification.md``). Local
state cannot tell you who churned during that window: the users table
still says ``paid`` and no record of the missed event survives. Stripe is
the only source of truth, so the drift has to be repaired by walking
Stripe and diffing.

Run this once after deploying the webhook fix, and keep it around as a
periodic audit — a webhook that silently no-ops is exactly the failure
mode that motivated it.

Usage
-----
    # Dry run (default): report drift, change nothing.
    python backend/scripts/reconcile_subscriptions.py \
        --table pixel-prompt-users --region us-west-2

    # Apply corrections after reviewing the dry-run output.
    python backend/scripts/reconcile_subscriptions.py \
        --table pixel-prompt-users --region us-west-2 --apply

Requires ``STRIPE_SECRET_KEY`` in the environment and AWS credentials with
read (and, for ``--apply``, write) access to the users table.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import boto3
import stripe

# Stripe subscription statuses that should map to the paid tier.
_PAID_STATUSES = frozenset({"active", "trialing"})

# userId prefixes that are not real users.
_SYNTHETIC_PREFIXES = (
    "guest#",
    "model#",
    "metrics#",
    "revenue#",
    "config#",
    "event#",
    "prompt#",
)


def _is_real_user(user_id: str) -> bool:
    return not any(user_id.startswith(p) for p in _SYNTHETIC_PREFIXES)


def _scan_users(table: Any) -> list[dict]:
    """Return every real user record in the table."""
    users: list[dict] = []
    kwargs: dict[str, Any] = {}
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            if _is_real_user(str(item.get("userId", ""))):
                users.append(item)
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return users


def _stripe_status_for_customer(customer_id: str) -> tuple[str | None, str | None]:
    """Return (status, subscription_id) for a customer's newest subscription.

    ``status=None`` means the customer has no subscriptions at all.
    """
    try:
        subs = stripe.Subscription.list(customer=customer_id, status="all", limit=10)
    except stripe.error.InvalidRequestError:
        # Customer deleted or unknown to this Stripe account.
        return None, None
    data = sorted(
        subs.get("data", []),
        key=lambda s: s.get("created", 0),
        reverse=True,
    )
    if not data:
        return None, None
    newest = data[0]
    return newest.get("status"), newest.get("id")


def _expected_tier(status: str | None) -> str:
    return "paid" if status in _PAID_STATUSES else "free"


def reconcile(table_name: str, region: str, apply: bool) -> int:
    """Diff DynamoDB tier state against Stripe. Returns a process exit code."""
    secret = os.environ.get("STRIPE_SECRET_KEY", "")
    if not secret:
        print("ERROR: STRIPE_SECRET_KEY is not set", file=sys.stderr)
        return 2
    stripe.api_key = secret

    if secret.startswith("sk_live_"):
        print("!! Running against LIVE Stripe data.\n")

    table = boto3.resource("dynamodb", region_name=region).Table(table_name)
    users = _scan_users(table)
    print(f"Scanned {len(users)} user records from {table_name}\n")

    drift: list[dict] = []
    no_customer = 0

    for user in users:
        user_id = str(user["userId"])
        local_tier = str(user.get("tier", "free"))
        customer_id = user.get("stripeCustomerId")

        if not customer_id:
            # Never checked out. Only notable if they somehow hold paid tier.
            if local_tier == "paid":
                drift.append(
                    {
                        "userId": user_id,
                        "localTier": local_tier,
                        "stripeStatus": "no-customer",
                        "expectedTier": "free",
                        "subscriptionId": "",
                    }
                )
            else:
                no_customer += 1
            continue

        status, sub_id = _stripe_status_for_customer(str(customer_id))
        expected = _expected_tier(status)
        if expected != local_tier:
            drift.append(
                {
                    "userId": user_id,
                    "localTier": local_tier,
                    "stripeStatus": status or "no-subscription",
                    "expectedTier": expected,
                    "subscriptionId": sub_id or "",
                }
            )

    print(f"{no_customer} users have never checked out (skipped)")
    if not drift:
        print("No drift found — DynamoDB agrees with Stripe.")
        return 0

    over = [d for d in drift if d["localTier"] == "paid" and d["expectedTier"] == "free"]
    under = [d for d in drift if d["localTier"] == "free" and d["expectedTier"] == "paid"]

    print(f"\nDRIFT: {len(drift)} record(s)")
    print(f"  {len(over):>4} granted paid access they should not have (missed cancellation)")
    print(f"  {len(under):>4} denied paid access they are paying for")
    print()
    header = f"{'userId':<40} {'local':<6} -> {'expected':<9} {'stripe status':<20} subscription"
    print(header)
    print("-" * len(header))
    for d in sorted(drift, key=lambda x: (x["expectedTier"], x["userId"])):
        print(
            f"{d['userId']:<40} {d['localTier']:<6} -> {d['expectedTier']:<9} "
            f"{d['stripeStatus']:<20} {d['subscriptionId']}"
        )

    if not apply:
        print("\nDRY RUN — nothing was modified. Re-run with --apply to correct.")
        return 1

    print(f"\nApplying {len(drift)} correction(s)...")
    import time

    applied = 0
    for d in drift:
        try:
            table.update_item(
                Key={"userId": d["userId"]},
                UpdateExpression=("SET tier = :t, subscriptionStatus = :s, updatedAt = :now"),
                ExpressionAttributeValues={
                    ":t": d["expectedTier"],
                    ":s": d["stripeStatus"],
                    ":now": int(time.time()),
                },
            )
            applied += 1
        except Exception as e:  # noqa: BLE001 - report and continue
            print(f"  FAILED {d['userId']}: {e}", file=sys.stderr)

    print(f"Applied {applied}/{len(drift)} correction(s).")
    if applied != len(drift):
        return 1

    print(
        "\nNOTE: revenue counters (activeSubscribers / monthlyChurn) are NOT "
        "adjusted here — they are aggregates, and blindly decrementing them "
        "per corrected user would compound the drift rather than fix it. "
        "Recompute them from the corrected tier counts instead."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--table",
        default=os.environ.get("USERS_TABLE_NAME", "pixel-prompt-users"),
        help="DynamoDB users table name",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", "us-west-2"),
        help="AWS region",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write corrections. Without this the script only reports.",
    )
    args = parser.parse_args()
    return reconcile(args.table, args.region, args.apply)


if __name__ == "__main__":
    sys.exit(main())
