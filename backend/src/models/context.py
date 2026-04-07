"""
Conversation context management for iterative image refinement.
Maintains a rolling 3-iteration context window per model column.
"""

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from jobs.manager import ConcurrencyError
from utils.logger import StructuredLogger


@dataclass
class ContextEntry:
    """A single entry in the conversation context window."""

    iteration: int
    prompt: str
    image_key: str
    timestamp: str  # ISO8601 format


class ContextManager:
    """
    Manages rolling 3-iteration conversation context per model column.

    Context is stored in S3 at: sessions/{session_id}/context/{model}.json

    The window maintains the last 3 iterations to provide context for
    conversational refinement without excessive token costs.
    """

    WINDOW_SIZE = 3

    def __init__(self, s3_client, bucket: str):
        """
        Initialize context manager.

        Args:
            s3_client: Boto3 S3 client
            bucket: S3 bucket name
        """
        self.s3 = s3_client
        self.bucket = bucket

    def _get_context_key(self, session_id: str, model: str) -> str:
        """Generate S3 key for context file."""
        return f"sessions/{session_id}/context/{model}.json"

    def get_context(self, session_id: str, model: str) -> List[ContextEntry]:
        """
        Load context window from S3.

        Args:
            session_id: Session identifier
            model: Model name ('gemini', 'nova', 'openai', 'firefly')

        Returns:
            List of ContextEntry objects (empty if no context exists)
        """
        key = self._get_context_key(session_id, model)

        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            data = json.loads(response["Body"].read().decode("utf-8"))

            # Parse context entries
            entries = []
            for item in data.get("window", []):
                try:
                    entries.append(
                        ContextEntry(
                            iteration=item["iteration"],
                            prompt=item["prompt"],
                            image_key=item["imageKey"],
                            timestamp=item.get("timestamp", ""),
                        )
                    )
                except (KeyError, TypeError) as e:
                    StructuredLogger.warning(
                        f"Skipping malformed context entry: {e}",
                        session_id=session_id,
                        model=model,
                    )

            return entries

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                # No context file exists yet - this is normal for new sessions
                return []
            raise

        except json.JSONDecodeError as e:
            StructuredLogger.warning(
                f"Corrupted context JSON for {session_id}/{model}: {e}",
                session_id=session_id,
                model=model,
            )
            return []

        except Exception as e:
            StructuredLogger.error(
                f"Error loading context for {session_id}/{model}: {e}",
                session_id=session_id,
                model=model,
            )
            raise

    def add_entry(self, session_id: str, model: str, entry: ContextEntry) -> None:
        """
        Add entry to context, maintaining window size.

        Uses FIFO (first-in-first-out) to keep only the last 3 entries.
        Retries on ETag conflict (context is append-only so merge is safe).
        """
        max_retries = 3
        for _attempt in range(max_retries):
            key = self._get_context_key(session_id, model)
            etag = None

            try:
                resp = self.s3.get_object(Bucket=self.bucket, Key=key)
                etag = resp.get("ETag")
                data = json.loads(resp["Body"].read().decode("utf-8"))
                entries = []
                for item in data.get("window", []):
                    try:
                        entries.append(
                            ContextEntry(
                                iteration=item["iteration"],
                                prompt=item["prompt"],
                                image_key=item["imageKey"],
                                timestamp=item.get("timestamp", ""),
                            )
                        )
                    except (KeyError, TypeError):
                        pass
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchKey":
                    entries = []
                else:
                    raise
            except (json.JSONDecodeError, KeyError, TypeError):
                entries = []

            entries.append(entry)
            if len(entries) > self.WINDOW_SIZE:
                entries = entries[-self.WINDOW_SIZE :]

            if self._save_context_conditional(session_id, model, entries, etag):
                return

            time.sleep(0.05 * (_attempt + 1))

        raise ConcurrencyError(
            f"Failed to add context entry after {max_retries} retries for {session_id}/{model}"
        )

    def _save_context_conditional(
        self,
        session_id: str,
        model: str,
        entries: List[ContextEntry],
        expected_etag: Optional[str] = None,
    ) -> bool:
        """Save context with ETag-based conditional write. Returns True on success."""
        key = self._get_context_key(session_id, model)
        body = json.dumps(
            {
                "model": model,
                "sessionId": session_id,
                "window": [
                    {
                        "iteration": e.iteration,
                        "prompt": e.prompt,
                        "imageKey": e.image_key,
                        "timestamp": e.timestamp,
                    }
                    for e in entries
                ],
            }
        )

        try:
            put_kwargs = {
                "Bucket": self.bucket,
                "Key": key,
                "Body": body,
                "ContentType": "application/json",
            }
            if expected_etag:
                put_kwargs["IfMatch"] = expected_etag
            else:
                put_kwargs["IfNoneMatch"] = "*"

            self.s3.put_object(**put_kwargs)
            return True
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("PreconditionFailed", "412"):
                return False
            raise

    def get_context_for_iteration(self, session_id: str, model: str) -> List[Dict[str, Any]]:
        """
        Get context in format suitable for model iteration handlers.

        Returns list of dicts with 'prompt' and 'imageKey' for each
        context entry, ordered oldest to newest.

        Args:
            session_id: Session identifier
            model: Model name

        Returns:
            List of context dicts for handler consumption
        """
        entries = self.get_context(session_id, model)
        return [
            {
                "iteration": e.iteration,
                "prompt": e.prompt,
                "imageKey": e.image_key,
                "timestamp": e.timestamp,
            }
            for e in entries
        ]


def create_context_entry(iteration: int, prompt: str, image_key: str) -> ContextEntry:
    """
    Factory function to create a new ContextEntry with current timestamp.

    Args:
        iteration: Iteration index (0 for original, 1+ for iterations)
        prompt: The prompt used for this iteration
        image_key: S3 key of the generated image

    Returns:
        New ContextEntry instance
    """
    return ContextEntry(
        iteration=iteration,
        prompt=prompt,
        image_key=image_key,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
