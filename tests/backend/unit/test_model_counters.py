"""Tests for ops.model_counters.ModelCounterService using moto."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws
from unittest.mock import patch

from users.repository import UserRepository

TABLE = "pixel-prompt-users"


@pytest.fixture
def users_table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield TABLE, ddb


def _repo(users_table):
    return UserRepository(users_table[0], dynamodb_resource=users_table[1])


def test_increment_under_cap_returns_true(users_table):
    from ops.model_counters import ModelCounterService

    repo = _repo(users_table)
    svc = ModelCounterService(repo)
    now = 1_000_000
    ok, item = svc.increment_model_count("gemini", now)
    assert ok is True
    assert int(item.get("dailyCount", 0)) == 1


def test_increment_at_cap_returns_false(users_table):
    from ops.model_counters import ModelCounterService

    repo = _repo(users_table)
    svc = ModelCounterService(repo)
    now = 1_000_000
    with patch("config.MODEL_DAILY_CAPS", {"gemini": 2, "nova": 500, "openai": 500, "firefly": 500}):
        svc.increment_model_count("gemini", now)
        svc.increment_model_count("gemini", now + 1)
        ok, item = svc.increment_model_count("gemini", now + 2)
        assert ok is False
        assert int(item.get("dailyCount", 0)) == 2


def test_window_reset_after_24h(users_table):
    from ops.model_counters import ModelCounterService

    repo = _repo(users_table)
    svc = ModelCounterService(repo)
    now = 1_000_000
    with patch("config.MODEL_DAILY_CAPS", {"gemini": 1, "nova": 500, "openai": 500, "firefly": 500}):
        ok1, _ = svc.increment_model_count("gemini", now)
        assert ok1 is True
        ok2, _ = svc.increment_model_count("gemini", now + 100)
        assert ok2 is False
        # After 24h window expires, counter should reset
        ok3, item = svc.increment_model_count("gemini", now + 86401)
        assert ok3 is True
        assert int(item.get("dailyCount", 0)) == 1


def test_get_model_counts_returns_all_models(users_table):
    from ops.model_counters import ModelCounterService

    repo = _repo(users_table)
    svc = ModelCounterService(repo)
    now = 1_000_000
    counts = svc.get_model_counts(now)
    assert set(counts.keys()) == {"gemini", "nova", "openai", "firefly"}
    for model_name, data in counts.items():
        assert "dailyCount" in data
        assert "cap" in data


def test_get_model_counts_with_existing_data(users_table):
    from ops.model_counters import ModelCounterService

    repo = _repo(users_table)
    svc = ModelCounterService(repo)
    now = 1_000_000
    svc.increment_model_count("gemini", now)
    svc.increment_model_count("gemini", now + 1)
    counts = svc.get_model_counts(now + 2)
    assert counts["gemini"]["dailyCount"] == 2
    assert counts["nova"]["dailyCount"] == 0


def test_check_model_allowed_convenience(users_table):
    from ops.model_counters import ModelCounterService

    repo = _repo(users_table)
    svc = ModelCounterService(repo)
    now = 1_000_000
    assert svc.check_model_allowed("gemini", now) is True


def test_model_counter_uses_model_prefix_key(users_table):
    from ops.model_counters import ModelCounterService

    repo = _repo(users_table)
    svc = ModelCounterService(repo)
    now = 1_000_000
    svc.increment_model_count("gemini", now)
    # Verify the item is stored with model# prefix
    item = repo.get_user("model#gemini")
    assert item is not None
    assert int(item["dailyCount"]) == 1
