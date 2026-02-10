"""
Unit tests for the SessionManager class.

Uses moto mock_s3 fixture for real S3 behavior instead of MagicMock.
Tests assert on observable behavior (data in S3) not call_args.
"""

import pytest

from jobs.manager import SessionManager


class TestSessionManager:
    """Tests for SessionManager functionality using moto-backed S3."""

    @pytest.fixture
    def session_manager(self, mock_s3):
        """Create a SessionManager backed by moto S3."""
        s3, bucket = mock_s3
        return SessionManager(s3, bucket)

    def test_create_session_returns_uuid(self, session_manager):
        """create_session() should return a valid UUID."""
        import uuid

        session_id = session_manager.create_session("test prompt", ["flux", "gemini"])
        uuid.UUID(session_id)  # Raises ValueError if invalid

    def test_create_and_retrieve_session(self, session_manager):
        """create_session() stores data retrievable via get_session()."""
        sid = session_manager.create_session("sunset", ["flux", "gemini"])
        session = session_manager.get_session(sid)

        assert session is not None
        assert session["prompt"] == "sunset"
        assert session["status"] == "pending"
        assert session["models"]["flux"]["enabled"] is True
        assert session["models"]["gemini"]["enabled"] is True

    def test_create_session_marks_disabled_models(self, session_manager):
        """Models not in enabled list should be marked disabled."""
        sid = session_manager.create_session("test prompt", ["flux"])
        session = session_manager.get_session(sid)

        assert session["models"]["flux"]["enabled"] is True
        assert session["models"]["flux"]["status"] == "pending"
        assert session["models"]["recraft"]["enabled"] is False
        assert session["models"]["recraft"]["status"] == "disabled"

    def test_get_session_returns_none_for_missing(self, session_manager):
        """get_session() should return None for nonexistent session."""
        result = session_manager.get_session("nonexistent")
        assert result is None

    def test_add_iteration_increments_count(self, session_manager):
        """add_iteration() should create an in-progress iteration in S3."""
        sid = session_manager.create_session("test", ["flux"])
        index = session_manager.add_iteration(sid, "flux", "refine prompt")

        assert index == 0

        session = session_manager.get_session(sid)
        assert session["models"]["flux"]["iterationCount"] == 1
        assert len(session["models"]["flux"]["iterations"]) == 1
        assert session["models"]["flux"]["iterations"][0]["status"] == "in_progress"

    def test_add_iteration_rejects_at_limit(self, session_manager):
        """add_iteration() should reject when iteration limit reached."""
        sid = session_manager.create_session("test", ["flux"])

        # Add 7 iterations to reach the limit
        for i in range(7):
            session_manager.add_iteration(sid, "flux", f"prompt {i}")
            session_manager.complete_iteration(sid, "flux", i, f"key-{i}", 1.0)

        with pytest.raises(ValueError, match="(?i)limit"):
            session_manager.add_iteration(sid, "flux", "one too many")

    def test_complete_iteration_stores_image_key(self, session_manager):
        """complete_iteration() should store image key and update status."""
        sid = session_manager.create_session("test", ["flux"])
        session_manager.add_iteration(sid, "flux", "prompt")

        session_manager.complete_iteration(sid, "flux", 0, "image-key-123", 5.5)

        session = session_manager.get_session(sid)
        iteration = session["models"]["flux"]["iterations"][0]
        assert iteration["status"] == "completed"
        assert iteration["imageKey"] == "image-key-123"
        assert iteration["duration"] == 5.5

    def test_fail_iteration_stores_error(self, session_manager):
        """fail_iteration() should store error message."""
        sid = session_manager.create_session("test", ["flux"])
        session_manager.add_iteration(sid, "flux", "prompt")

        session_manager.fail_iteration(sid, "flux", 0, "API error")

        session = session_manager.get_session(sid)
        iteration = session["models"]["flux"]["iterations"][0]
        assert iteration["status"] == "error"
        assert iteration["error"] == "API error"

    def test_get_iteration_count(self, session_manager):
        """get_iteration_count() should return correct count."""
        sid = session_manager.create_session("test", ["flux"])
        assert session_manager.get_iteration_count(sid, "flux") == 0

        session_manager.add_iteration(sid, "flux", "p1")
        assert session_manager.get_iteration_count(sid, "flux") == 1

        session_manager.add_iteration(sid, "flux", "p2")
        assert session_manager.get_iteration_count(sid, "flux") == 2

    def test_get_latest_image_key(self, session_manager):
        """get_latest_image_key() should return most recent completed image key."""
        sid = session_manager.create_session("test", ["flux"])

        # No completed iterations yet
        assert session_manager.get_latest_image_key(sid, "flux") is None

        # Add and complete two iterations
        session_manager.add_iteration(sid, "flux", "p1")
        session_manager.complete_iteration(sid, "flux", 0, "key-0", 1.0)

        session_manager.add_iteration(sid, "flux", "p2")
        session_manager.complete_iteration(sid, "flux", 1, "key-1", 1.0)

        # Add a third in-progress (no imageKey yet)
        session_manager.add_iteration(sid, "flux", "p3")

        assert session_manager.get_latest_image_key(sid, "flux") == "key-1"
