"""
Unit tests for the ContextManager class.
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestContextManager:
    """Tests for ContextManager functionality."""

    @pytest.fixture
    def mock_s3_client(self):
        """Create a mock S3 client."""
        mock = MagicMock()
        mock.exceptions = MagicMock()
        mock.exceptions.NoSuchKey = type('NoSuchKey', (Exception,), {})
        return mock

    @pytest.fixture
    def context_manager(self, mock_s3_client):
        """Create a ContextManager with mock S3."""
        from models.context import ContextManager
        return ContextManager(mock_s3_client, 'test-bucket')

    def test_get_context_returns_empty_for_new_session(self, context_manager, mock_s3_client):
        """get_context() should return empty list for new session."""
        # Simulate NoSuchKey error
        mock_s3_client.get_object.side_effect = mock_s3_client.exceptions.NoSuchKey()

        result = context_manager.get_context('session-123', 'flux')

        assert result == []

    def test_get_context_returns_entries(self, context_manager, mock_s3_client):
        """get_context() should return parsed entries from S3."""
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

        mock_s3_client.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(context_data).encode('utf-8'))
        }

        result = context_manager.get_context('session-123', 'flux')

        assert len(result) == 2
        assert result[0].iteration == 0
        assert result[0].prompt == 'test prompt 1'
        assert result[1].iteration == 1

    def test_add_entry_maintains_window_size(self, context_manager, mock_s3_client):
        """add_entry() should maintain max 3 entries in window."""
        # Existing context with 3 entries
        existing_data = {
            'window': [
                {'iteration': i, 'prompt': f'prompt {i}', 'imageKey': f'key-{i}', 'timestamp': '2024-01-01T00:00:00Z'}
                for i in range(3)
            ]
        }

        mock_s3_client.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(existing_data).encode('utf-8'))
        }

        from models.context import create_context_entry
        new_entry = create_context_entry(3, 'new prompt', 'new-key')

        context_manager.add_entry('session-123', 'flux', new_entry)

        # Verify put_object was called
        mock_s3_client.put_object.assert_called_once()
        call_args = mock_s3_client.put_object.call_args

        # Parse saved data
        saved_data = json.loads(call_args.kwargs['Body'])
        assert len(saved_data['window']) == 3  # Max window size

        # Oldest entry (iteration 0) should be removed
        iterations = [e['iteration'] for e in saved_data['window']]
        assert 0 not in iterations
        assert 3 in iterations

    def test_clear_context(self, context_manager, mock_s3_client):
        """clear_context() should delete context file from S3."""
        context_manager.clear_context('session-123', 'flux')

        mock_s3_client.delete_object.assert_called_once()
        call_args = mock_s3_client.delete_object.call_args
        assert call_args.kwargs['Key'] == 'sessions/session-123/context/flux.json'

    def test_get_context_for_iteration(self, context_manager, mock_s3_client):
        """get_context_for_iteration() should return handler-compatible format."""
        context_data = {
            'window': [
                {
                    'iteration': 0,
                    'prompt': 'test prompt',
                    'imageKey': 'key-0',
                    'timestamp': '2024-01-01T00:00:00Z'
                }
            ]
        }

        mock_s3_client.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(context_data).encode('utf-8'))
        }

        result = context_manager.get_context_for_iteration('session-123', 'flux')

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['prompt'] == 'test prompt'
        assert result[0]['imageKey'] == 'key-0'

    def test_handles_corrupted_json(self, context_manager, mock_s3_client):
        """get_context() should handle corrupted JSON gracefully."""
        mock_s3_client.get_object.return_value = {
            'Body': MagicMock(read=lambda: b'not valid json')
        }

        result = context_manager.get_context('session-123', 'flux')

        assert result == []


class TestCreateContextEntry:
    """Tests for create_context_entry factory function."""

    def test_creates_entry_with_timestamp(self):
        """create_context_entry() should create entry with current timestamp."""
        from models.context import create_context_entry

        entry = create_context_entry(2, 'test prompt', 'test-key')

        assert entry.iteration == 2
        assert entry.prompt == 'test prompt'
        assert entry.image_key == 'test-key'
        assert '+00:00' in entry.timestamp or entry.timestamp.endswith('Z')  # ISO8601 UTC
