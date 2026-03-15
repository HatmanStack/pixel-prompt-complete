"""
Unit tests for the ContextManager class.

Uses moto mock_s3 fixture for real S3 behavior instead of MagicMock.
Tests assert on observable behavior (data in S3) not call_args.
"""

import json
import pytest

from models.context import ContextManager, create_context_entry


class TestContextManager:
    """Tests for ContextManager functionality using moto-backed S3."""

    @pytest.fixture
    def context_manager(self, mock_s3):
        """Create a ContextManager backed by moto S3."""
        s3, bucket = mock_s3
        return ContextManager(s3, bucket)

    def test_get_context_returns_empty_for_new_session(self, context_manager):
        """get_context() should return empty list for new session."""
        result = context_manager.get_context('session-123', 'flux')
        assert result == []

    def test_get_context_returns_entries(self, context_manager, mock_s3):
        """get_context() should return parsed entries from S3."""
        s3, bucket = mock_s3
        context_data = {
            'window': [
                {
                    'iteration': 0,
                    'prompt': 'test prompt 1',
                    'imageKey': 'sessions/123/images/flux-0.png',
                    'timestamp': '2024-01-01T00:00:00Z'
                },
                {
                    'iteration': 1,
                    'prompt': 'test prompt 2',
                    'imageKey': 'sessions/123/images/flux-1.png',
                    'timestamp': '2024-01-01T00:01:00Z'
                }
            ]
        }
        s3.put_object(
            Bucket=bucket,
            Key='sessions/session-123/context/flux.json',
            Body=json.dumps(context_data),
            ContentType='application/json',
        )

        result = context_manager.get_context('session-123', 'flux')

        assert len(result) == 2
        assert result[0].iteration == 0
        assert result[0].prompt == 'test prompt 1'
        assert result[1].iteration == 1

    def test_add_entry_creates_context_for_new_session(self, context_manager, mock_s3):
        """add_entry() should create context file when none exists."""
        s3, bucket = mock_s3
        entry = create_context_entry(0, 'first prompt', 'key-0')

        context_manager.add_entry('session-new', 'flux', entry)

        # Verify data stored in S3
        obj = s3.get_object(
            Bucket=bucket,
            Key='sessions/session-new/context/flux.json',
        )
        data = json.loads(obj['Body'].read().decode('utf-8'))
        assert len(data['window']) == 1
        assert data['window'][0]['prompt'] == 'first prompt'
        assert data['window'][0]['iteration'] == 0

    def test_add_entry_maintains_window_size(self, context_manager, mock_s3):
        """add_entry() should maintain max 3 entries in window (FIFO eviction)."""
        # Add 4 entries; only the last 3 should remain
        for i in range(4):
            entry = create_context_entry(i, f'prompt {i}', f'key-{i}')
            context_manager.add_entry('session-123', 'flux', entry)

        result = context_manager.get_context('session-123', 'flux')

        assert len(result) == 3
        # Oldest entry (iteration 0) should have been evicted
        iterations = [e.iteration for e in result]
        assert 0 not in iterations
        assert iterations == [1, 2, 3]

    def test_get_context_for_iteration(self, context_manager):
        """get_context_for_iteration() should return handler-compatible dicts."""
        entry = create_context_entry(0, 'test prompt', 'key-0')
        context_manager.add_entry('session-123', 'flux', entry)

        result = context_manager.get_context_for_iteration('session-123', 'flux')

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['prompt'] == 'test prompt'
        assert result[0]['imageKey'] == 'key-0'
        assert 'iteration' in result[0]
        assert 'timestamp' in result[0]

    def test_handles_corrupted_json(self, context_manager, mock_s3):
        """get_context() should handle corrupted JSON gracefully."""
        s3, bucket = mock_s3
        s3.put_object(
            Bucket=bucket,
            Key='sessions/session-123/context/flux.json',
            Body=b'not valid json',
            ContentType='application/json',
        )

        result = context_manager.get_context('session-123', 'flux')
        assert result == []

    def test_separate_context_per_model(self, context_manager):
        """Each model should have independent context."""
        entry_flux = create_context_entry(0, 'flux prompt', 'flux-key')
        entry_gemini = create_context_entry(0, 'gemini prompt', 'gemini-key')

        context_manager.add_entry('session-123', 'flux', entry_flux)
        context_manager.add_entry('session-123', 'gemini', entry_gemini)

        flux_ctx = context_manager.get_context('session-123', 'flux')
        gemini_ctx = context_manager.get_context('session-123', 'gemini')

        assert len(flux_ctx) == 1
        assert flux_ctx[0].prompt == 'flux prompt'
        assert len(gemini_ctx) == 1
        assert gemini_ctx[0].prompt == 'gemini prompt'


class TestCreateContextEntry:
    """Tests for create_context_entry factory function."""

    def test_creates_entry_with_timestamp(self):
        """create_context_entry() should create entry with current timestamp."""
        entry = create_context_entry(2, 'test prompt', 'test-key')

        assert entry.iteration == 2
        assert entry.prompt == 'test prompt'
        assert entry.image_key == 'test-key'
        assert '+00:00' in entry.timestamp or entry.timestamp.endswith('Z')  # ISO8601 UTC
