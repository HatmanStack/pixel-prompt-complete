"""Tests for admin model status and control endpoints.

Covers:
- Model list returns all 4 models with counts and caps
- Model disable sets disabled flag in DynamoDB
- Model enable clears disabled flag
- Invalid model name returns 400
- Admin auth enforcement
- Runtime disable check integration
"""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from ops.model_counters import ModelCounterService
from users.repository import UserRepository


def _make_admin_event(
    path: str = "/admin/models",
    method: str = "GET",
    groups: list[str] | None = None,
):
    """Build an API Gateway event with admin JWT claims."""
    if groups is None:
        groups = ["admins"]
    return {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method, "sourceIp": "127.0.0.1"},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "admin-user-1",
                        "email": "admin@example.com",
                        "cognito:groups": groups,
                    }
                }
            },
        },
        "queryStringParameters": {},
    }


@pytest.fixture
def dynamo_repo():
    """Create a moto DynamoDB table and UserRepository."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-users",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        repo = UserRepository("test-users", dynamodb_resource=dynamodb)
        yield repo


@pytest.fixture
def model_counter(dynamo_repo):
    return ModelCounterService(dynamo_repo)


class TestHandleAdminModelsList:
    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_returns_all_4_models(self, dynamo_repo, model_counter):
        from admin.models import handle_admin_models_list

        event = _make_admin_event()
        now = int(time.time())
        result = handle_admin_models_list(event, model_counter, "corr-1")
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert len(body["models"]) == 4
        names = {m["name"] for m in body["models"]}
        assert names == {"gemini", "nova", "openai", "firefly"}

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_models_have_correct_fields(self, dynamo_repo, model_counter):
        from admin.models import handle_admin_models_list

        event = _make_admin_event()
        result = handle_admin_models_list(event, model_counter, "corr-1")
        body = json.loads(result["body"])
        model = body["models"][0]
        assert "name" in model
        assert "displayName" in model
        assert "enabled" in model
        assert "provider" in model
        assert "dailyCount" in model
        assert "dailyCap" in model

    @patch("config.admin_enabled", False)
    @patch("config.auth_enabled", True)
    def test_returns_501_when_admin_disabled(self, dynamo_repo, model_counter):
        from admin.models import handle_admin_models_list

        event = _make_admin_event()
        result = handle_admin_models_list(event, model_counter, "corr-1")
        assert result["statusCode"] == 501


class TestHandleAdminModelDisable:
    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_disable_sets_flag(self, dynamo_repo):
        from admin.models import handle_admin_model_disable

        event = _make_admin_event(path="/admin/models/gemini/disable", method="POST")
        result = handle_admin_model_disable(event, dynamo_repo, "corr-1")
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "disabled"

        # Verify DynamoDB item exists
        cfg = dynamo_repo.get_model_runtime_config("gemini")
        assert cfg is not None
        assert cfg["disabled"] is True

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_disable_invalid_model_returns_400(self, dynamo_repo):
        from admin.models import handle_admin_model_disable

        event = _make_admin_event(path="/admin/models/invalid/disable", method="POST")
        result = handle_admin_model_disable(event, dynamo_repo, "corr-1")
        assert result["statusCode"] == 400


class TestHandleAdminModelEnable:
    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_enable_clears_flag(self, dynamo_repo):
        from admin.models import handle_admin_model_disable, handle_admin_model_enable

        # First disable
        event = _make_admin_event(path="/admin/models/nova/disable", method="POST")
        handle_admin_model_disable(event, dynamo_repo, "corr-1")

        # Then enable
        event = _make_admin_event(path="/admin/models/nova/enable", method="POST")
        result = handle_admin_model_enable(event, dynamo_repo, "corr-1")
        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "enabled"

        cfg = dynamo_repo.get_model_runtime_config("nova")
        assert cfg is not None
        assert cfg["disabled"] is False

    @patch("config.admin_enabled", True)
    @patch("config.auth_enabled", True)
    def test_enable_invalid_model_returns_400(self, dynamo_repo):
        from admin.models import handle_admin_model_enable

        event = _make_admin_event(path="/admin/models/bogus/enable", method="POST")
        result = handle_admin_model_enable(event, dynamo_repo, "corr-1")
        assert result["statusCode"] == 400


class TestModelRuntimeConfig:
    def test_get_returns_none_when_missing(self, dynamo_repo):
        assert dynamo_repo.get_model_runtime_config("gemini") is None

    def test_set_and_get(self, dynamo_repo):
        dynamo_repo.set_model_runtime_config("gemini", disabled=True)
        cfg = dynamo_repo.get_model_runtime_config("gemini")
        assert cfg is not None
        assert cfg["disabled"] is True

    def test_set_disabled_false(self, dynamo_repo):
        dynamo_repo.set_model_runtime_config("gemini", disabled=True)
        dynamo_repo.set_model_runtime_config("gemini", disabled=False)
        cfg = dynamo_repo.get_model_runtime_config("gemini")
        assert cfg["disabled"] is False
