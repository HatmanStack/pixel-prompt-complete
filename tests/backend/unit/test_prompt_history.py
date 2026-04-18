"""
Unit tests for prompt history DynamoDB repository and API endpoints.
"""

import json
import os
import time
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from prompts.repository import PromptHistoryRepository

# Ensure env vars are set before any lambda_function import
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

_REPO_TABLE_NAME = "test-prompt-history"


@pytest.fixture
def dynamodb_table():
    """Create a mock DynamoDB table with the PromptHistoryIndex GSI.

    Each test gets its own mock_aws context so no state leaks between tests or modules.
    """
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName=_REPO_TABLE_NAME,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "promptOwner", "AttributeType": "S"},
                {"AttributeName": "createdAt", "AttributeType": "N"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "PromptHistoryIndex",
                    "KeySchema": [
                        {"AttributeName": "promptOwner", "KeyType": "HASH"},
                        {"AttributeName": "createdAt", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.meta.client.get_waiter("table_exists").wait(TableName=_REPO_TABLE_NAME)
        yield dynamodb, _REPO_TABLE_NAME


@pytest.fixture
def repo(dynamodb_table):
    dynamodb, table_name = dynamodb_table
    return PromptHistoryRepository(table_name, dynamodb_resource=dynamodb)


class TestPromptHistoryRepository:
    def test_record_prompt_writes_global_feed(self, repo, dynamodb_table):
        """Record with user_id=None, query global feed, verify item exists."""
        repo.record_prompt(user_id=None, prompt="sunset over ocean", session_id="sess-1")

        feed = repo.get_recent_feed()
        assert len(feed) == 1
        assert feed[0]["prompt"] == "sunset over ocean"
        assert feed[0]["sessionId"] == "sess-1"

    def test_record_prompt_writes_both_for_authenticated(self, repo, dynamodb_table):
        """Record with user_id, query both feeds, verify items."""
        repo.record_prompt(user_id="user-abc", prompt="mountain landscape", session_id="sess-2")

        feed = repo.get_recent_feed()
        assert len(feed) == 1
        assert feed[0]["prompt"] == "mountain landscape"

        history = repo.get_user_history("user-abc")
        assert len(history) == 1
        assert history[0]["prompt"] == "mountain landscape"
        assert history[0]["sessionId"] == "sess-2"

    def test_get_user_history_newest_first(self, repo, dynamodb_table, monkeypatch):
        """Record 5 prompts with patched timestamps, verify ordering."""
        base_time = 1700000000
        for i in range(5):
            monkeypatch.setattr(time, "time", lambda _i=i: base_time + _i)
            repo.record_prompt(
                user_id="user-order",
                prompt=f"prompt {i}",
                session_id=f"sess-{i}",
            )

        history = repo.get_user_history("user-order")
        assert len(history) == 5
        # Newest first: createdAt should be strictly descending
        for i in range(len(history) - 1):
            assert history[i]["createdAt"] > history[i + 1]["createdAt"]

    def test_get_user_history_limit(self, repo, dynamodb_table):
        """Record 10 prompts, request limit=3, verify only 3 returned."""
        for i in range(10):
            repo.record_prompt(
                user_id="user-limit",
                prompt=f"prompt {i}",
                session_id=f"sess-{i}",
            )

        history = repo.get_user_history("user-limit", limit=3)
        assert len(history) == 3

    def test_get_recent_feed(self, repo, dynamodb_table):
        """Record several prompts from different users, verify all appear in feed."""
        repo.record_prompt(user_id="user-a", prompt="prompt A", session_id="sess-a")
        repo.record_prompt(user_id="user-b", prompt="prompt B", session_id="sess-b")
        repo.record_prompt(user_id=None, prompt="prompt C", session_id="sess-c")

        feed = repo.get_recent_feed()
        assert len(feed) == 3
        prompts = {item["prompt"] for item in feed}
        assert prompts == {"prompt A", "prompt B", "prompt C"}

    def test_search_user_history(self, repo, dynamodb_table):
        """Record prompts with distinct words, search for one, verify only matching returned."""
        repo.record_prompt(user_id="user-search", prompt="sunset over ocean", session_id="s1")
        repo.record_prompt(user_id="user-search", prompt="mountain landscape", session_id="s2")
        repo.record_prompt(user_id="user-search", prompt="city skyline at night", session_id="s3")

        results = repo.search_user_history("user-search", "mountain")
        assert len(results) == 1
        assert results[0]["prompt"] == "mountain landscape"

    def test_feed_items_have_ttl(self, repo, dynamodb_table):
        """Record a prompt, verify the global item has ttl attribute set."""
        repo.record_prompt(user_id=None, prompt="test ttl", session_id="sess-ttl")

        dynamodb, table_name = dynamodb_table
        table = dynamodb.Table(table_name)

        # Scan for the global feed item
        response = table.scan(
            FilterExpression="promptOwner = :po",
            ExpressionAttributeValues={":po": "GLOBAL#RECENT"},
        )
        items = response["Items"]
        assert len(items) == 1
        assert "ttl" in items[0]
        # TTL should be approximately 7 days from now
        expected_ttl = int(time.time()) + 7 * 86400
        assert abs(items[0]["ttl"] - expected_ttl) < 10  # within 10 seconds

    def test_user_items_have_ttl(self, repo, dynamodb_table):
        """Record a prompt with user_id, verify user item has 90-day ttl."""
        repo.record_prompt(user_id="user-ttl", prompt="expires in 90d", session_id="s1")

        dynamodb, table_name = dynamodb_table
        table = dynamodb.Table(table_name)

        response = table.scan(
            FilterExpression="promptOwner = :po",
            ExpressionAttributeValues={":po": "USER#user-ttl"},
        )
        items = response["Items"]
        assert len(items) == 1
        assert "ttl" in items[0]
        # TTL should be ~90 days from now
        assert int(items[0]["ttl"]) > int(items[0]["createdAt"]) + 80 * 86400


# --- Endpoint integration tests ---

_MOD = "lambda_function"
_TARGETS = [
    f"{_MOD}.s3_client",
    f"{_MOD}.session_manager",
    f"{_MOD}.context_manager",
    f"{_MOD}.image_storage",
    f"{_MOD}.content_filter",
    f"{_MOD}.prompt_enhancer",
    f"{_MOD}._executor",
    f"{_MOD}._gallery_executor",
    f"{_MOD}.get_enabled_models",
    f"{_MOD}.get_handler",
    f"{_MOD}.get_iterate_handler",
    f"{_MOD}.get_outpaint_handler",
    f"{_MOD}.get_model",
    f"{_MOD}.get_model_config_dict",
    f"{_MOD}.handle_log",
]


def _make_event(method="POST", path="/generate", body=None, source_ip="1.2.3.4",
                query_params=None):
    event = {
        "rawPath": path,
        "requestContext": {"http": {"method": method, "sourceIp": source_ip}},
        "headers": {},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    if query_params:
        event["queryStringParameters"] = query_params
    return event


def _body(resp):
    return json.loads(resp["body"])


@pytest.fixture
def ep_mocks():
    """Patch module-level singletons for endpoint tests.

    Wraps in mock_aws so lambda_function import (if not yet cached) can create
    boto3 clients without hitting real AWS.
    """
    with mock_aws():
        # Ensure the S3 bucket exists for lambda_function module-level init
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")

        patchers = []
        m = {}
        for target in _TARGETS:
            p = patch(target)
            obj = p.start()
            patchers.append(p)
            m[target.split(".")[-1]] = obj

        m["content_filter"].check_prompt.return_value = False
        m["get_enabled_models"].return_value = []

        yield m

        for p in patchers:
            p.stop()


def _get_lambda_handler():
    """Import lambda_handler inside mock_aws to avoid module-level AWS calls leaking."""
    from lambda_function import lambda_handler
    return lambda_handler


class TestPromptEndpoints:
    """Tests for /prompts/recent and /prompts/history endpoints."""

    def test_prompts_recent_endpoint(self, ep_mocks):
        """Call the recent endpoint, verify response structure."""
        lambda_handler = _get_lambda_handler()
        mock_repo = MagicMock()
        mock_repo.get_recent_feed.return_value = [
            {"prompt": "sunset", "sessionId": "s1", "createdAt": 1000},
        ]

        with patch("lambda_function._prompt_history", mock_repo):
            resp = lambda_handler(
                _make_event(method="GET", path="/prompts/recent"), None
            )

        assert resp["statusCode"] == 200
        body = _body(resp)
        assert "prompts" in body
        assert len(body["prompts"]) == 1
        assert body["prompts"][0]["prompt"] == "sunset"

    def test_prompts_history_requires_auth(self, ep_mocks):
        """Call /prompts/history without auth, verify 501 (auth disabled)."""
        lambda_handler = _get_lambda_handler()
        with patch("lambda_function.config") as mock_config:
            mock_config.auth_enabled = False
            mock_config.cors_allowed_origin = "*"
            resp = lambda_handler(
                _make_event(method="GET", path="/prompts/history"), None
            )

        assert resp["statusCode"] == 501

    def test_prompts_recent_with_limit(self, ep_mocks):
        """Call /prompts/recent with limit param."""
        lambda_handler = _get_lambda_handler()
        mock_repo = MagicMock()
        mock_repo.get_recent_feed.return_value = []

        with patch("lambda_function._prompt_history", mock_repo):
            resp = lambda_handler(
                _make_event(
                    method="GET", path="/prompts/recent",
                    query_params={"limit": "10"}
                ),
                None,
            )

        assert resp["statusCode"] == 200
        mock_repo.get_recent_feed.assert_called_once_with(limit=10)

    @patch("lambda_function.as_completed")
    def test_generate_records_prompt(self, mock_as_completed, ep_mocks):
        """Call handle_generate, verify prompt was recorded."""
        lambda_handler = _get_lambda_handler()
        fake_model = MagicMock(name="gemini", provider="google_gemini")
        fake_model.name = "gemini"
        ep_mocks["get_enabled_models"].return_value = [fake_model]
        ep_mocks["session_manager"].create_session.return_value = "sess-rec"
        ep_mocks["get_model_config_dict"].return_value = {"id": "gemini-model"}
        ep_mocks["prompt_enhancer"].adapt_per_model.return_value = {
            "gemini": "sunset"
        }
        ep_mocks["session_manager"].add_iteration.return_value = 0
        ep_mocks["get_handler"].return_value = lambda c, p, params: {
            "status": "success", "image": "b64",
        }
        ep_mocks["image_storage"].upload_image.return_value = "k"
        ep_mocks["image_storage"].get_cloudfront_url.return_value = "https://cdn/k"

        def submit_sync(fn, model):
            result = fn(model)
            future = MagicMock()
            future.result.return_value = result
            return future

        ep_mocks["_executor"].submit.side_effect = submit_sync
        mock_as_completed.side_effect = lambda futures, **kwargs: futures.keys()

        mock_repo = MagicMock()
        with patch("lambda_function._prompt_history", mock_repo):
            resp = lambda_handler(_make_event(body={"prompt": "sunset"}), None)

        assert resp["statusCode"] == 200
        mock_repo.record_prompt.assert_called_once()
        call_args = mock_repo.record_prompt.call_args
        assert call_args.kwargs.get("prompt") == "sunset" or call_args[1].get("prompt") == "sunset"

    @patch("lambda_function.as_completed")
    def test_generate_survives_history_write_failure(self, mock_as_completed, ep_mocks):
        """Mock record_prompt to raise, verify generation still succeeds."""
        lambda_handler = _get_lambda_handler()
        fake_model = MagicMock(name="gemini", provider="google_gemini")
        fake_model.name = "gemini"
        ep_mocks["get_enabled_models"].return_value = [fake_model]
        ep_mocks["session_manager"].create_session.return_value = "sess-fail"
        ep_mocks["get_model_config_dict"].return_value = {"id": "gemini-model"}
        ep_mocks["prompt_enhancer"].adapt_per_model.return_value = {
            "gemini": "sunset"
        }
        ep_mocks["session_manager"].add_iteration.return_value = 0
        ep_mocks["get_handler"].return_value = lambda c, p, params: {
            "status": "success", "image": "b64",
        }
        ep_mocks["image_storage"].upload_image.return_value = "k"
        ep_mocks["image_storage"].get_cloudfront_url.return_value = "https://cdn/k"

        def submit_sync(fn, model):
            result = fn(model)
            future = MagicMock()
            future.result.return_value = result
            return future

        ep_mocks["_executor"].submit.side_effect = submit_sync
        mock_as_completed.side_effect = lambda futures, **kwargs: futures.keys()

        mock_repo = MagicMock()
        mock_repo.record_prompt.side_effect = Exception("DynamoDB error")
        with patch("lambda_function._prompt_history", mock_repo):
            resp = lambda_handler(_make_event(body={"prompt": "sunset"}), None)

        # Generation should still succeed despite history write failure
        assert resp["statusCode"] == 200
