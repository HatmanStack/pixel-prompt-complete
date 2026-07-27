"""
Session Manager for Pixel Prompt v2.

Manages session lifecycle with iteration tracking per model column.
Replaces the previous job-based storage with session-centric storage.
"""

from __future__ import annotations

import json
import random
import time
import uuid
from datetime import datetime, timezone
from typing import TypedDict

from botocore.exceptions import ClientError

from config import MAX_ITERATIONS, MODELS

# Attempts at the conditional write before giving up. Was 3, which is thin
# against four provider threads issuing eight conflicting writes per
# generation -- and the write that loses is `complete_iteration`, i.e. an
# image already generated, paid for and uploaded.
MAX_RETRIES = 8
# Base for the exponential backoff, in milliseconds.
#
# The arithmetic matters, because a lock that waits long enough becomes the
# timeout it was meant to survive. Sleeps happen after every attempt but the
# last, so seven of them: 25 * (2**0 + ... + 2**6) = 25 * 127 = 3175ms, plus
# up to 7 * 25 = 175ms of jitter. Worst case ~3.35s against a
# `generate_dispatch_budget_seconds` of 70 -- under 5%, and only on a request
# that is about to fail anyway.
RETRY_BASE_DELAY_MS = 25


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff with jitter, in seconds, for attempt ``attempt``.

    Jitter is what stops four threads that collided once from colliding again
    on the same schedule; without it, retrying writers stay in lockstep and
    the extra attempts buy nothing.
    """
    jitter = random.uniform(0, RETRY_BASE_DELAY_MS)
    return (RETRY_BASE_DELAY_MS * (2.0**attempt) + jitter) / 1000.0


class _IterationRequired(TypedDict):
    index: int
    status: str


class Iteration(_IterationRequired, total=False):
    """One refinement of one model column.

    Only ``index`` and ``status`` are required: they are the two fields every
    reader dereferences unconditionally. Everything else is written on some
    paths and not others -- ``imageKey`` and ``duration`` only on success,
    ``error`` only on failure, ``adaptedPrompt`` only when adaptation changed
    the prompt -- and records already in S3 reflect that.
    """

    prompt: str
    startedAt: str
    isOutpaint: bool
    adaptedPrompt: str
    outpaintPreset: str
    imageKey: str
    completedAt: str
    duration: float
    error: str


class ModelColumn(TypedDict):
    """One model's column within a session. Always written in full."""

    enabled: bool
    status: str
    iterationCount: int
    iterations: list[Iteration]


class _SessionRequired(TypedDict):
    sessionId: str
    status: str
    version: int
    prompt: str
    createdAt: str
    updatedAt: str
    models: dict[str, ModelColumn]


class SessionState(_SessionRequired, total=False):
    """The stored shape of ``sessions/{id}/status.json``.

    ``ownerId`` and ``visibility`` are optional because sessions written
    before those features existed carry neither -- ``lambda_function.
    _session_is_private`` already reasons about exactly that case. Marking
    them required would assert a shape that historical records in S3 do not
    have.
    """

    ownerId: str | None
    visibility: str


class ConcurrencyError(Exception):
    """Raised when optimistic locking retries are exhausted."""

    pass


class SessionManager:
    """
    Manages image generation sessions with iteration tracking per model.

    Sessions are stored in S3 at: sessions/{session_id}/status.json

    Each session tracks:
    - Original prompt
    - 4 model columns (gemini, nova, openai, firefly)
    - Up to 7 iterations per model
    - Status per model and overall

    **The lock is the S3 ETag, not the ``version`` field.** ``version`` is
    read, incremented and persisted on every mutation, and appears in no
    condition anywhere -- it is an advisory counter, useful for spotting a
    lost update after the fact and for reasoning about one while debugging.
    What actually serialises concurrent writers is
    ``_save_status_if_unmodified``, which passes the ETag from the read that
    produced the state as ``IfMatch``. The field named for the lock has never
    been the lock; the name is kept because the counter earns its place, and
    this docstring exists so the name stops misleading readers.

    The four provider threads are deliberately NOT serialised behind a local
    ``threading.Lock``. It would work, and it would make the four provider
    calls' session writes strictly sequential to avoid contention that now
    costs two round trips per attempt and resolves within the retry budget --
    trading real parallelism for a problem the ETag already solves.
    """

    def __init__(self, s3_client, bucket_name: str):
        """
        Initialize Session Manager.

        Args:
            s3_client: boto3 S3 client
            bucket_name: S3 bucket name for session storage
        """
        self.s3 = s3_client
        self.bucket = bucket_name

    def create_session(
        self,
        prompt: str,
        enabled_models: list[str],
        owner_id: str | None = None,
        visibility: str = "public",
    ) -> str:
        """
        Create a new session with the given enabled models.

        Args:
            prompt: Original text prompt
            enabled_models: List of enabled model names ('gemini', 'nova', etc.)
            owner_id: Caller identity, recorded so a private session can be
                authorized on read. Sessions previously recorded no owner at
                all, which is why nothing could enforce access to one.
            visibility: ``"public"`` or ``"private"``. Determines both the S3
                prefix the images land under and whether the prompt reaches the
                global feed.

        Returns:
            Session ID (UUID)
        """
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Initialize model states for all 4 models
        models: dict[str, ModelColumn] = {}
        for model_name in MODELS.keys():
            models[model_name] = {
                "enabled": model_name in enabled_models,
                "status": "pending" if model_name in enabled_models else "disabled",
                "iterationCount": 0,
                "iterations": [],
            }

        status: SessionState = {
            "sessionId": session_id,
            "status": "pending",
            "version": 1,
            "prompt": prompt,
            "createdAt": now,
            "updatedAt": now,
            "ownerId": owner_id,
            "visibility": visibility,
            "models": models,
        }

        self._save_status(session_id, status)
        return session_id

    def _get_session_with_etag(self, session_id: str) -> tuple[SessionState, str] | None:
        """Read the session and the ETag that identifies the version read.

        The ETag is what the subsequent conditional write is guarded on. It is
        returned from the SAME response that produced the state on purpose:
        fetching it separately with a second HEAD request cost a third round trip
        and, worse, opened a window in which another writer could land between
        the two -- so ``IfMatch`` guarded a version this reader never read, and
        the conflict it was meant to detect went undetected.

        Returns None when the session does not exist.
        """
        try:
            key = f"sessions/{session_id}/status.json"
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            state: SessionState = json.loads(response["Body"].read().decode("utf-8"))
            return state, response["ETag"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    def get_session(self, session_id: str) -> dict | None:
        """
        Get session status from S3.

        Args:
            session_id: Session identifier

        Returns:
            Session status dict or None if not found
        """
        loaded = self._get_session_with_etag(session_id)
        return dict(loaded[0]) if loaded else None

    def add_iteration(
        self,
        session_id: str,
        model: str,
        prompt: str,
        is_outpaint: bool = False,
        outpaint_preset: str | None = None,
        adapted_prompt: str | None = None,
    ) -> int:
        """
        Add a new iteration to a model column.

        Args:
            session_id: Session identifier
            model: Model name ('gemini', 'nova', 'openai', 'firefly')
            prompt: Iteration prompt
            is_outpaint: Whether this is an outpaint operation
            outpaint_preset: Outpaint preset if applicable
            adapted_prompt: Model-specific prompt after adaptation (stored as
                ``adaptedPrompt`` when it differs from ``prompt``; None to skip)

        Returns:
            New iteration index

        Raises:
            ValueError: If session/model not found or iteration limit reached
        """
        for attempt in range(MAX_RETRIES):
            loaded = self._get_session_with_etag(session_id)
            if not loaded:
                raise ValueError(f"Session {session_id} not found")
            session, etag = loaded

            if model not in session["models"]:
                raise ValueError(f"Unknown model: {model}")

            model_data = session["models"][model]
            if not model_data["enabled"]:
                raise ValueError(f"Model '{model}' is disabled")

            # Check iteration limit
            if model_data["iterationCount"] >= MAX_ITERATIONS:
                raise ValueError(f"Iteration limit ({MAX_ITERATIONS}) reached for model '{model}'")

            original_version = session.get("version", 1)
            iteration_index = model_data["iterationCount"]
            now = datetime.now(timezone.utc).isoformat()

            # Add iteration
            iteration: Iteration = {
                "index": iteration_index,
                "status": "in_progress",
                "prompt": prompt,
                "startedAt": now,
                "isOutpaint": is_outpaint,
            }
            if adapted_prompt and adapted_prompt != prompt:
                iteration["adaptedPrompt"] = adapted_prompt
            if outpaint_preset:
                iteration["outpaintPreset"] = outpaint_preset

            model_data["iterations"].append(iteration)
            model_data["iterationCount"] = iteration_index + 1
            model_data["status"] = "in_progress"

            # Update session
            session["status"] = self._compute_session_status(session)
            session["updatedAt"] = now
            session["version"] = original_version + 1

            if self._save_status_if_unmodified(session_id, session, etag):
                return iteration_index

            if attempt < MAX_RETRIES - 1:
                time.sleep(_backoff_seconds(attempt))

        raise ConcurrencyError(
            f"Failed to add iteration after {MAX_RETRIES} retries for session {session_id}"
        )

    def complete_iteration(
        self,
        session_id: str,
        model: str,
        index: int,
        image_key: str,
        duration: float | None = None,
    ) -> None:
        """
        Mark an iteration as completed with image key.

        Args:
            session_id: Session identifier
            model: Model name
            index: Iteration index
            image_key: S3 key of generated image
            duration: Processing duration in seconds (optional)
        """
        for attempt in range(MAX_RETRIES):
            loaded = self._get_session_with_etag(session_id)
            if not loaded:
                raise ValueError(f"Session {session_id} not found")
            session, etag = loaded

            original_version = session.get("version", 1)
            model_data = session["models"][model]

            # Find iteration
            iteration = None
            for it in model_data["iterations"]:
                if it["index"] == index:
                    iteration = it
                    break

            if not iteration:
                raise ValueError(f"Iteration {index} not found for model '{model}'")

            now = datetime.now(timezone.utc).isoformat()
            iteration["status"] = "completed"
            iteration["imageKey"] = image_key
            iteration["completedAt"] = now
            if duration is not None:
                iteration["duration"] = duration

            # Update model status
            model_data["status"] = self._compute_model_status(model_data)

            # Update session
            session["status"] = self._compute_session_status(session)
            session["updatedAt"] = now
            session["version"] = original_version + 1

            if self._save_status_if_unmodified(session_id, session, etag):
                return

            if attempt < MAX_RETRIES - 1:
                time.sleep(_backoff_seconds(attempt))

        raise ConcurrencyError(
            f"Failed to complete iteration after {MAX_RETRIES} retries for session {session_id}"
        )

    def fail_iteration(self, session_id: str, model: str, index: int, error: str) -> None:
        """
        Mark an iteration as failed with error message.

        Args:
            session_id: Session identifier
            model: Model name
            index: Iteration index
            error: Error message
        """
        for attempt in range(MAX_RETRIES):
            loaded = self._get_session_with_etag(session_id)
            if not loaded:
                raise ValueError(f"Session {session_id} not found")
            session, etag = loaded

            original_version = session.get("version", 1)
            model_data = session["models"][model]

            # Find iteration
            iteration = None
            for it in model_data["iterations"]:
                if it["index"] == index:
                    iteration = it
                    break

            if not iteration:
                raise ValueError(f"Iteration {index} not found for model '{model}'")

            now = datetime.now(timezone.utc).isoformat()
            iteration["status"] = "error"
            iteration["error"] = error
            iteration["completedAt"] = now

            # Update model status
            model_data["status"] = self._compute_model_status(model_data)

            # Update session
            session["status"] = self._compute_session_status(session)
            session["updatedAt"] = now
            session["version"] = original_version + 1

            if self._save_status_if_unmodified(session_id, session, etag):
                return

            if attempt < MAX_RETRIES - 1:
                time.sleep(_backoff_seconds(attempt))

        raise ConcurrencyError(
            f"Failed to fail iteration after {MAX_RETRIES} retries for session {session_id}"
        )

    def get_iteration_count(self, session_id: str, model: str) -> int:
        """
        Get current iteration count for a model.

        Args:
            session_id: Session identifier
            model: Model name

        Returns:
            Current iteration count (0-7)
        """
        loaded = self._get_session_with_etag(session_id)
        if not loaded:
            return 0

        model_data = loaded[0]["models"].get(model)
        if not model_data:
            return 0

        return model_data.get("iterationCount", 0)

    def get_latest_image_key(self, session_id: str, model: str) -> str | None:
        """
        Get the image key of the latest completed iteration.

        Args:
            session_id: Session identifier
            model: Model name

        Returns:
            S3 image key or None if no completed iterations
        """
        loaded = self._get_session_with_etag(session_id)
        if not loaded:
            return None

        model_data = loaded[0]["models"].get(model)
        if not model_data:
            return None

        # Find latest completed iteration
        completed = [
            it
            for it in model_data["iterations"]
            if it["status"] == "completed" and "imageKey" in it
        ]

        if not completed:
            return None

        # Return the one with highest index
        latest = max(completed, key=lambda x: x["index"])
        return latest.get("imageKey")

    def _save_status(self, session_id: str, status: SessionState) -> None:
        """Save session status to S3 (unconditional write for new sessions)."""
        key = f"sessions/{session_id}/status.json"
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(status),
            ContentType="application/json",
        )

    def _save_status_if_unmodified(
        self,
        session_id: str,
        status: SessionState,
        etag: str,
    ) -> bool:
        """Write the status, conditional on nobody having written since ``etag``.

        Named for what it does rather than for ``status["version"]``. The
        version field is advisory and appears in no condition; ``etag`` is the
        lock. See the class docstring.

        ``etag`` must come from the read that produced ``status`` -- passing a
        separately fetched one guards against a version the caller never saw.

        Returns True if the write landed, False if another writer won.
        """
        key = f"sessions/{session_id}/status.json"
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=json.dumps(status),
                ContentType="application/json",
                IfMatch=etag,
            )
            return True
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("PreconditionFailed", "412"):
                return False
            raise

    def _compute_model_status(self, model_data: ModelColumn) -> str:
        """Compute status for a single model based on its iterations."""
        if not model_data["enabled"]:
            return "disabled"

        iterations = model_data["iterations"]
        if not iterations:
            return "pending"

        # Check if any in progress
        if any(it["status"] == "in_progress" for it in iterations):
            return "in_progress"

        # All iterations complete
        has_error = any(it["status"] == "error" for it in iterations)
        has_completed = any(it["status"] == "completed" for it in iterations)

        if has_error and not has_completed:
            return "error"
        elif has_error:
            return "partial"
        else:
            return "completed"

    def _compute_session_status(self, session: SessionState) -> str:
        """Compute overall session status from model statuses."""
        models = session["models"]
        enabled_models = [m for m in models.values() if m["enabled"]]

        if not enabled_models:
            return "failed"

        statuses = [m["status"] for m in enabled_models]

        if any(s == "in_progress" for s in statuses):
            return "in_progress"

        if any(s == "pending" for s in statuses):
            return "pending"

        # All done (no pending or in_progress)
        error_count = sum(1 for s in statuses if s in ["error", "failed"])

        if error_count == len(enabled_models):
            return "failed"
        elif error_count > 0:
            return "partial"
        else:
            return "completed"
