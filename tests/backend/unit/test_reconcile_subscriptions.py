"""Tests for the Stripe reconciliation script.

The script repairs drift left behind by the cancellation-webhook bug, so it
is the last line of defence for users who churned while that bug was live.
It must be exercised, not just shipped.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

TABLE_NAME = "pixel-prompt-users-reconcile"

_SCRIPT = (
    pathlib.Path(__file__).resolve().parents[3]
    / "backend"
    / "scripts"
    / "reconcile_subscriptions.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("reconcile_subscriptions", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["reconcile_subscriptions"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def script():
    return _load_script()


@pytest.fixture
def table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield ddb.Table(TABLE_NAME)


def _put(table, user_id, tier, customer=None):
    item = {"userId": user_id, "tier": tier}
    if customer:
        item["stripeCustomerId"] = customer
    table.put_item(Item=item)


def _fake_sub(status, sub_id="sub_x", created=100):
    return {"status": status, "id": sub_id, "created": created}


def test_is_real_user_filters_synthetic_records(script):
    assert script._is_real_user("cognito-sub-123")
    for prefix in (
        "guest#",
        "model#",
        "metrics#",
        "revenue#",
        "config#",
        "event#",
        "prompt#",
    ):
        assert not script._is_real_user(f"{prefix}whatever")


def test_expected_tier_mapping(script):
    assert script._expected_tier("active") == "paid"
    assert script._expected_tier("trialing") == "paid"
    assert script._expected_tier("canceled") == "free"
    assert script._expected_tier("past_due") == "free"
    assert script._expected_tier(None) == "free"


def test_missing_stripe_key_exits_2(script, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    assert script.reconcile(TABLE_NAME, "us-east-1", apply=False) == 2


def test_detects_missed_cancellation_in_dry_run(script, table, monkeypatch, capsys):
    """The exact drift the webhook bug produced: local paid, Stripe canceled."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    _put(table, "churned-user", "paid", "cus_churn")

    fake_list = MagicMock(return_value={"data": [_fake_sub("canceled", "sub_churn")]})
    with patch.object(script.stripe.Subscription, "list", fake_list):
        rc = script.reconcile(TABLE_NAME, "us-east-1", apply=False)

    assert rc == 1
    out = capsys.readouterr().out
    assert "churned-user" in out
    assert "DRY RUN" in out
    # Dry run must not write.
    assert table.get_item(Key={"userId": "churned-user"})["Item"]["tier"] == "paid"


def test_apply_corrects_tier(script, table, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    _put(table, "churned-user", "paid", "cus_churn")

    fake_list = MagicMock(return_value={"data": [_fake_sub("canceled", "sub_churn")]})
    with patch.object(script.stripe.Subscription, "list", fake_list):
        rc = script.reconcile(TABLE_NAME, "us-east-1", apply=True)

    assert rc == 0
    item = table.get_item(Key={"userId": "churned-user"})["Item"]
    assert item["tier"] == "free"
    assert item["subscriptionStatus"] == "canceled"


def test_no_drift_returns_zero(script, table, monkeypatch, capsys):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    _put(table, "good-user", "paid", "cus_good")

    fake_list = MagicMock(return_value={"data": [_fake_sub("active", "sub_good")]})
    with patch.object(script.stripe.Subscription, "list", fake_list):
        rc = script.reconcile(TABLE_NAME, "us-east-1", apply=False)

    assert rc == 0
    assert "No drift found" in capsys.readouterr().out


def test_paid_without_customer_is_drift(script, table, monkeypatch):
    """Paid tier with no Stripe customer at all can never be legitimate."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    _put(table, "ghost-paid", "paid")

    rc = script.reconcile(TABLE_NAME, "us-east-1", apply=True)
    assert rc == 0
    assert table.get_item(Key={"userId": "ghost-paid"})["Item"]["tier"] == "free"


def test_underprovisioned_user_is_upgraded(script, table, monkeypatch):
    """Drift runs both ways: a paying user stuck on free must be restored."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    _put(table, "paying-user", "free", "cus_paying")

    fake_list = MagicMock(return_value={"data": [_fake_sub("active", "sub_paying")]})
    with patch.object(script.stripe.Subscription, "list", fake_list):
        rc = script.reconcile(TABLE_NAME, "us-east-1", apply=True)

    assert rc == 0
    assert table.get_item(Key={"userId": "paying-user"})["Item"]["tier"] == "paid"


def test_synthetic_records_are_ignored(script, table, monkeypatch, capsys):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    for uid in (
        "guest#abc",
        "revenue#current",
        "event#evt_1",
        "prompt#p1",
        "config#model#gemini",
    ):
        table.put_item(Item={"userId": uid, "tier": "paid"})

    rc = script.reconcile(TABLE_NAME, "us-east-1", apply=False)
    assert rc == 0
    assert "Scanned 0 user records" in capsys.readouterr().out


def test_newest_subscription_wins(script, table, monkeypatch):
    """A customer who resubscribed must be read from their newest sub."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    _put(table, "resubbed", "free", "cus_resub")

    fake_list = MagicMock(
        return_value={
            "data": [
                _fake_sub("canceled", "sub_old", created=100),
                _fake_sub("active", "sub_new", created=999),
            ]
        }
    )
    with patch.object(script.stripe.Subscription, "list", fake_list):
        rc = script.reconcile(TABLE_NAME, "us-east-1", apply=True)

    assert rc == 0
    assert table.get_item(Key={"userId": "resubbed"})["Item"]["tier"] == "paid"


def test_unknown_customer_is_treated_as_free(script, table, monkeypatch):
    """A customer Stripe no longer knows about must not keep paid access."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    _put(table, "deleted-customer", "paid", "cus_gone")

    def raise_invalid(**kwargs):
        raise script.stripe.error.InvalidRequestError("No such customer", "customer")

    with patch.object(script.stripe.Subscription, "list", raise_invalid):
        rc = script.reconcile(TABLE_NAME, "us-east-1", apply=True)

    assert rc == 0
    assert table.get_item(Key={"userId": "deleted-customer"})["Item"]["tier"] == "free"
