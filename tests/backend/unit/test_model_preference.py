"""Tests for per-user model preference capture.

Generating produces four images the user did not choose between. Refining one
is the first moment they express a preference, and it costs them credits,
which makes it a stronger signal than a click or a download.

Nothing recorded this before: the data was derivable from session history but
never aggregated, so the product could not answer "which model suits you".
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFRONT_DOMAIN", "test.cloudfront.net")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

TABLE = "pixel-prompt-users-pref"


@pytest.fixture
def repo():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        from users.repository import UserRepository

        yield UserRepository(TABLE, dynamodb_resource=ddb)


def test_a_choice_is_counted(repo):
    repo.record_model_choice("u1", "gemini")
    assert repo.get_model_choices("u1") == {"gemini": 1}


def test_choices_accumulate_per_model(repo):
    for _ in range(3):
        repo.record_model_choice("u1", "firefly")
    repo.record_model_choice("u1", "nova")
    assert repo.get_model_choices("u1") == {"firefly": 3, "nova": 1}


def test_choices_are_ordered_by_preference(repo):
    """The first entry is the answer to "which model wins for you"."""
    repo.record_model_choice("u1", "nova")
    for _ in range(5):
        repo.record_model_choice("u1", "openai")
    for _ in range(2):
        repo.record_model_choice("u1", "gemini")

    assert list(repo.get_model_choices("u1")) == ["openai", "gemini", "nova"]


def test_preference_is_per_user(repo):
    repo.record_model_choice("u1", "gemini")
    repo.record_model_choice("u2", "firefly")
    assert repo.get_model_choices("u1") == {"gemini": 1}
    assert repo.get_model_choices("u2") == {"firefly": 1}


def test_anonymous_choices_are_not_recorded(repo):
    """There is no person to attribute an anonymous preference to."""
    repo.record_model_choice("anon", "gemini")
    repo.record_model_choice("", "gemini")
    assert repo.get_model_choices("anon") == {}


def test_no_choices_yet_reads_as_empty(repo):
    repo.get_or_create_user("fresh")
    assert repo.get_model_choices("fresh") == {}


def test_quota_counters_are_not_mistaken_for_choices(repo):
    """Only modelChoice* fields count; the user record holds much else."""
    repo.get_or_create_user("u1")
    repo.increment_generate("u1", 3600, 10, 1000)
    repo.record_model_choice("u1", "gemini")
    assert repo.get_model_choices("u1") == {"gemini": 1}


def test_refinement_records_the_chosen_model():
    """End to end through the refinement path."""
    import lambda_function
    from users.quota import QuotaResult
    from users.tier import TierContext

    tier = TierContext(
        tier="paid",
        user_id="u1",
        email=None,
        is_authenticated=True,
        guest_token_id=None,
        issue_guest_cookie=False,
    )
    model_cfg = MagicMock()
    model_cfg.name = "gemini"
    model_cfg.provider = "google_gemini"

    with (
        patch("config.auth_enabled", True),
        patch("lambda_function._guest_service", MagicMock()),
        patch("lambda_function._user_repo") as mock_repo,
        patch("lambda_function._model_counter_service") as mock_counter,
        patch("lambda_function.resolve_tier", return_value=tier),
        patch(
            "lambda_function._enforce_quota_safe",
            return_value=QuotaResult(allowed=True, reason=None, reset_at=0, usage={}),
        ),
        patch("lambda_function._daily_spend_exceeded", return_value=False),
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function._validate_refinement_request") as mock_val,
        patch("lambda_function._load_source_image") as mock_load,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function.context_manager", MagicMock()),
        patch("lambda_function._handle_successful_result", return_value={}),
        patch("lambda_function._cost_meter"),
        patch(
            "lambda_function.get_iterate_handler",
            return_value=MagicMock(return_value={"status": "success", "duration": 1.0}),
        ),
    ):
        mock_counter.consume_model_slot.return_value = True
        mock_cf.check_prompt.return_value = False
        mock_val.return_value = (("s1", "gemini", model_cfg), None)
        mock_load.return_value = (("img", 1, "public"), None)
        mock_sm.add_iteration.return_value = 1

        lambda_function.handle_iterate(
            {
                "body": json.dumps({"sessionId": "s1", "model": "gemini", "prompt": "bluer"}),
                "requestContext": {"http": {"sourceIp": "1.2.3.4"}},
                "headers": {},
            },
            "corr-1",
        )

    mock_repo.record_model_choice.assert_called_once_with("u1", "gemini")


def test_a_failed_refinement_records_no_preference():
    """A model that failed was not chosen; it was endured."""
    import lambda_function
    from users.quota import QuotaResult
    from users.tier import TierContext

    tier = TierContext(
        tier="paid",
        user_id="u1",
        email=None,
        is_authenticated=True,
        guest_token_id=None,
        issue_guest_cookie=False,
    )
    model_cfg = MagicMock()
    model_cfg.name = "gemini"
    model_cfg.provider = "google_gemini"

    with (
        patch("config.auth_enabled", True),
        patch("lambda_function._guest_service", MagicMock()),
        patch("lambda_function._user_repo") as mock_repo,
        patch("lambda_function._model_counter_service") as mock_counter,
        patch("lambda_function.resolve_tier", return_value=tier),
        patch(
            "lambda_function._enforce_quota_safe",
            return_value=QuotaResult(allowed=True, reason=None, reset_at=0, usage={}),
        ),
        patch("lambda_function._daily_spend_exceeded", return_value=False),
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function._validate_refinement_request") as mock_val,
        patch("lambda_function._load_source_image") as mock_load,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function.context_manager", MagicMock()),
        patch("lambda_function._handle_failed_result"),
        patch("lambda_function._cost_meter"),
        patch(
            "lambda_function.get_iterate_handler",
            return_value=MagicMock(return_value={"status": "error", "error": "boom"}),
        ),
    ):
        mock_counter.consume_model_slot.return_value = True
        mock_cf.check_prompt.return_value = False
        mock_val.return_value = (("s1", "gemini", model_cfg), None)
        mock_load.return_value = (("img", 1, "public"), None)
        mock_sm.add_iteration.return_value = 1

        lambda_function.handle_iterate(
            {
                "body": json.dumps({"sessionId": "s1", "model": "gemini", "prompt": "bluer"}),
                "requestContext": {"http": {"sourceIp": "1.2.3.4"}},
                "headers": {},
            },
            "corr-1",
        )

    mock_repo.record_model_choice.assert_not_called()
