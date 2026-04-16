"""
Unit tests for prompt history DynamoDB repository.
"""

import time

import boto3
import pytest
from moto import mock_aws

from prompts.repository import PromptHistoryRepository


@pytest.fixture
def dynamodb_table():
    """Create a mock DynamoDB table with the PromptHistoryIndex GSI."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-users",
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
        table.meta.client.get_waiter("table_exists").wait(TableName="test-users")
        yield dynamodb, "test-users"


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

    def test_get_user_history_newest_first(self, repo, dynamodb_table):
        """Record 5 prompts with different timestamps, verify ordering."""
        for i in range(5):
            repo.record_prompt(
                user_id="user-order",
                prompt=f"prompt {i}",
                session_id=f"sess-{i}",
            )
            # Ensure distinct createdAt values
            time.sleep(0.01)

        history = repo.get_user_history("user-order")
        assert len(history) == 5
        # Newest first: createdAt should be descending
        for i in range(len(history) - 1):
            assert history[i]["createdAt"] >= history[i + 1]["createdAt"]

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

    def test_user_items_have_no_ttl(self, repo, dynamodb_table):
        """Record a prompt with user_id, verify user item has no ttl."""
        repo.record_prompt(user_id="user-no-ttl", prompt="persist forever", session_id="s1")

        dynamodb, table_name = dynamodb_table
        table = dynamodb.Table(table_name)

        response = table.scan(
            FilterExpression="promptOwner = :po",
            ExpressionAttributeValues={":po": "USER#user-no-ttl"},
        )
        items = response["Items"]
        assert len(items) == 1
        assert "ttl" not in items[0]
