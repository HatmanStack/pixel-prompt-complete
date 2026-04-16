"""DynamoDB-backed prompt history repository.

Stores per-user prompt history and a global recent feed using a GSI
(``PromptHistoryIndex``) on the existing ``pixel-prompt-users`` table.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import boto3

# TTL for global feed items: 7 days
_FEED_TTL_SECONDS = 7 * 86400


class PromptHistoryRepository:
    """CRUD for prompt history records in DynamoDB."""

    def __init__(self, table_name: str, dynamodb_resource: Any | None = None) -> None:
        self.table_name = table_name
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self._table = self._dynamodb.Table(table_name)

    def record_prompt(
        self,
        user_id: str | None,
        prompt: str,
        session_id: str,
    ) -> None:
        """Write prompt history record(s) to DynamoDB.

        Always writes a global feed item (``GLOBAL#RECENT``).
        If ``user_id`` is provided, also writes a per-user item.
        """
        now = int(time.time())

        # Global feed item (with TTL)
        global_item = {
            "userId": f"prompt#{uuid4()}",
            "promptOwner": "GLOBAL#RECENT",
            "createdAt": now,
            "prompt": prompt,
            "sessionId": session_id,
            "ttl": now + _FEED_TTL_SECONDS,
        }

        items_to_write = [global_item]

        if user_id is not None:
            user_item = {
                "userId": f"prompt#{uuid4()}",
                "promptOwner": f"USER#{user_id}",
                "createdAt": now,
                "prompt": prompt,
                "sessionId": session_id,
            }
            items_to_write.append(user_item)

        # Batch write for efficiency
        with self._table.batch_writer() as batch:
            for item in items_to_write:
                batch.put_item(Item=item)

    def get_user_history(self, user_id: str, limit: int = 50) -> list[dict]:
        """Query per-user prompt history, newest first.

        Args:
            user_id: The Cognito sub (without ``USER#`` prefix).
            limit: Maximum items to return.

        Returns:
            List of prompt history items.
        """
        response = self._table.query(
            IndexName="PromptHistoryIndex",
            KeyConditionExpression="promptOwner = :po",
            ExpressionAttributeValues={":po": f"USER#{user_id}"},
            ScanIndexForward=False,
            Limit=limit,
        )
        return response.get("Items", [])

    def get_recent_feed(self, limit: int = 50) -> list[dict]:
        """Query the global recent prompt feed, newest first.

        Args:
            limit: Maximum items to return.

        Returns:
            List of prompt history items.
        """
        response = self._table.query(
            IndexName="PromptHistoryIndex",
            KeyConditionExpression="promptOwner = :po",
            ExpressionAttributeValues={":po": "GLOBAL#RECENT"},
            ScanIndexForward=False,
            Limit=limit,
        )
        return response.get("Items", [])

    def search_user_history(self, user_id: str, query: str, limit: int = 20) -> list[dict]:
        """Search per-user prompt history by substring match.

        Args:
            user_id: The Cognito sub (without ``USER#`` prefix).
            query: Substring to search for in prompts.
            limit: Maximum items to return.

        Returns:
            List of matching prompt history items.
        """
        response = self._table.query(
            IndexName="PromptHistoryIndex",
            KeyConditionExpression="promptOwner = :po",
            FilterExpression="contains(prompt, :q)",
            ExpressionAttributeValues={
                ":po": f"USER#{user_id}",
                ":q": query,
            },
            ScanIndexForward=False,
            Limit=limit,
        )
        return response.get("Items", [])
