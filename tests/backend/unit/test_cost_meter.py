"""Tests for dollar-denominated spend metering.

The point of this module is that the system can answer "what did today cost?"
in dollars. Every assertion here is about money being counted correctly, not
about calls being counted.
"""

from __future__ import annotations

import importlib
import os

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

TABLE_NAME = "pixel-prompt-users-costmeter"

# 2026-07-25T12:00:00Z — fixed so day bucketing is deterministic.
NOW = 1784980800


@pytest.fixture
def repo():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        from users.repository import UserRepository

        yield UserRepository(TABLE_NAME, dynamodb_resource=ddb)


@pytest.fixture
def meter(repo):
    from ops.cost_meter import CostMeter

    return CostMeter(repo)


def test_day_key_is_utc(meter):
    from ops.cost_meter import spend_item_key

    assert spend_item_key(NOW) == "spend#2026-07-25"


def test_records_total_and_per_label(meter):
    total = meter.record(
        costs={"gemini": 39000, "nova": 40000},
        tier="paid",
        user_id="u1",
        now=NOW,
    )
    assert total == 79000
    spend = meter.get_daily_spend(now=NOW)
    assert spend["totalMicros"] == 79000
    assert spend["geminiMicros"] == 39000
    assert spend["novaMicros"] == 40000


def test_tier_bucket_separates_free_from_paid(meter):
    """Free-tier spend is the largest exposure; it must be separable."""
    meter.record(costs={"gemini": 39000}, tier="free", user_id="u_free", now=NOW)
    meter.record(costs={"gemini": 39000}, tier="paid", user_id="u_paid", now=NOW)
    spend = meter.get_daily_spend(now=NOW)
    assert spend["totalMicros"] == 78000
    assert spend["freeTierMicros"] == 39000
    assert spend["paidTierMicros"] == 39000


def test_accumulates_across_requests(meter):
    for _ in range(5):
        meter.record(costs={"openai": 40000}, tier="paid", user_id="u1", now=NOW)
    assert meter.get_daily_spend(now=NOW)["totalMicros"] == 200000


def test_per_user_spend_recorded(meter, repo):
    meter.record(costs={"firefly": 70000}, tier="paid", user_id="u1", now=NOW)
    meter.record(costs={"firefly": 70000}, tier="paid", user_id="u1", now=NOW)
    assert int(repo.get_user("u1")["periodSpendMicros"]) == 140000


def test_anonymous_user_not_attributed(meter, repo):
    """auth-disabled requests have no user record to charge."""
    meter.record(costs={"gemini": 39000}, tier="paid", user_id="anon", now=NOW)
    assert repo.get_user("anon") is None
    assert meter.get_daily_spend(now=NOW)["totalMicros"] == 39000


def test_separate_days_do_not_mix(meter):
    meter.record(costs={"gemini": 39000}, tier="paid", user_id="u1", now=NOW)
    meter.record(costs={"gemini": 39000}, tier="paid", user_id="u1", now=NOW + 86400)
    assert meter.get_daily_spend(now=NOW)["totalMicros"] == 39000
    assert meter.get_daily_spend(now=NOW + 86400)["totalMicros"] == 39000


def test_zero_cost_is_not_written(meter):
    assert meter.record(costs={"gemini": 0}, tier="paid", user_id="u1", now=NOW) == 0
    assert meter.get_daily_spend(now=NOW) == {"totalMicros": 0}


def test_empty_day_reads_as_zero(meter):
    assert meter.get_daily_spend(now=NOW)["totalMicros"] == 0


def test_metering_failure_never_raises(meter, monkeypatch):
    """A metrics write must not fail a user's image generation."""

    def boom(*a, **k):
        raise RuntimeError("dynamo down")

    monkeypatch.setattr(meter._repo, "add_counters", boom)
    # Must not propagate.
    assert (
        meter.record(costs={"gemini": 39000}, tier="paid", user_id="u1", now=NOW)
        == 39000
    )


def test_record_models_prices_a_full_generate(meter):
    """One Generate click: 4 models + one gpt-4o adaptation."""
    import config

    total = meter.record_models(
        model_names=["gemini", "nova", "openai", "firefly"],
        operation="generate",
        tier="paid",
        user_id="u1",
        include_enhance=True,
        now=NOW,
    )
    expected = (
        config.model_cost_micros("gemini", "generate")
        + config.model_cost_micros("nova", "generate")
        + config.model_cost_micros("openai", "generate")
        + config.model_cost_micros("firefly", "generate")
        + config.enhance_cost_usd_micros
    )
    assert total == expected
    # Sanity-check the headline number the pricing model rests on.
    assert 170000 <= total <= 230000, (
        f"generate should be ~$0.17-0.23, got {total / 1e6}"
    )


def test_record_models_refine_is_far_cheaper_than_generate(meter):
    """The 4x generate/refine gap is the whole reason to count dollars."""
    gen = meter.record_models(
        model_names=["gemini", "nova", "openai", "firefly"],
        operation="generate",
        tier="paid",
        include_enhance=True,
        now=NOW,
    )
    ref = meter.record_models(
        model_names=["gemini"], operation="refine", tier="paid", now=NOW
    )
    assert ref * 3 < gen


def test_unknown_model_costs_zero_not_raises():
    import config

    assert config.model_cost_micros("nonexistent", "generate") == 0
    assert config.model_cost_micros("gemini", "nonexistent") == 0


def test_cost_table_is_env_overridable(monkeypatch):
    monkeypatch.setenv("COST_FIREFLY_GENERATE_USD_MICROS", "123456")
    import config

    importlib.reload(config)
    try:
        assert config.model_cost_micros("firefly", "generate") == 123456
    finally:
        monkeypatch.delenv("COST_FIREFLY_GENERATE_USD_MICROS", raising=False)
        importlib.reload(config)


def test_all_four_models_priced_for_every_operation():
    """A missing entry would silently meter that path at $0."""
    import config

    for model in ("gemini", "nova", "openai", "firefly"):
        for op in config.COST_OPERATIONS:
            assert config.model_cost_micros(model, op) > 0, f"{model}/{op} is unpriced"


def test_spend_records_excluded_from_user_scans(repo):
    """spend# items must not surface in the admin user list."""
    repo.get_or_create_user("real-user")
    repo.add_counters("spend#2026-07-25", {"totalMicros": 1000})
    users, _ = repo.scan_users(limit=50)
    assert [u["userId"] for u in users] == ["real-user"]


# ---------------------------------------------------------------------------
# _read_spend must not be switchable off by a stray attribute
#
# It int()-coerced every attribute of the spend item except userId, updatedAt
# and ttl. Any non-numeric attribute raised ValueError, which the three
# ceiling helpers catch and fail OPEN -- so the last guard against an
# unbounded provider bill could be disabled by an attribute nobody was
# reading, and the failure looked like a log line rather than an outage.
# ---------------------------------------------------------------------------


def _put(repo, key, attributes):
    repo._table.put_item(Item={"userId": key, **attributes})


def test_a_stray_string_attribute_does_not_raise_and_the_numbers_survive(repo, meter):
    from ops.cost_meter import spend_item_key

    _put(repo, spend_item_key(NOW), {"totalMicros": 500, "geminiMicros": 200, "note": "hello"})

    spend = meter.get_daily_spend(now=NOW)

    assert spend["totalMicros"] == 500
    assert spend["geminiMicros"] == 200
    assert "note" not in spend


def test_a_skipped_attribute_is_logged_at_warning(repo, meter, caplog):
    """A silently dropped attribute is how a coercion bug hides."""
    import logging

    from ops.cost_meter import spend_item_key

    _put(repo, spend_item_key(NOW), {"totalMicros": 500, "note": "hello"})

    with caplog.at_level(logging.WARNING):
        meter.get_daily_spend(now=NOW)

    assert any("note" in record.getMessage() for record in caplog.records)


def test_an_unreadable_total_raises_a_distinct_error_rather_than_reading_as_zero(repo, meter):
    """Zero spend and unknown spend are different facts.

    Returning 0 for a corrupt total would report "nothing spent today" to a
    ceiling whose whole job is to notice that something was.
    """
    import pytest as _pytest

    from ops.cost_meter import UnreadableSpendTotal, spend_item_key

    _put(repo, spend_item_key(NOW), {"totalMicros": "not-a-number"})

    with _pytest.raises(UnreadableSpendTotal):
        meter.get_daily_spend(now=NOW)


def test_an_unreadable_enhance_total_also_raises(repo, meter):
    """/enhance has its own sub-ceiling reading its own attribute."""
    import pytest as _pytest

    from ops.cost_meter import UnreadableSpendTotal, spend_item_key

    _put(repo, spend_item_key(NOW), {"totalMicros": 1, "enhanceMicros": []})

    with _pytest.raises(UnreadableSpendTotal):
        meter.get_daily_spend(now=NOW)


def test_a_missing_item_still_reads_as_zero(meter):
    """No item means nothing spent yet, which is a real answer, not a failure."""
    assert meter.get_daily_spend(now=NOW) == {"totalMicros": 0}
