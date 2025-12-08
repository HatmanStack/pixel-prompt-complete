"""
Unit tests for the SessionManager class.
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


class TestSessionManager:
    """Tests for SessionManager functionality."""

    @pytest.fixture
    def mock_s3_client(self):
        """Create a mock S3 client."""
        mock = MagicMock()
        return mock

    @pytest.fixture
    def session_manager(self, mock_s3_client):
        """Create a SessionManager with mock S3."""
        # Patch MAX_ITERATIONS to avoid import issues
        with patch.dict('sys.modules', {'config': MagicMock(MAX_ITERATIONS=7)}):
            from jobs.manager import SessionManager
            return SessionManager(mock_s3_client, 'test-bucket')

    def test_create_session_returns_uuid(self, session_manager):
        """create_session() should return a valid UUID."""
        session_id = session_manager.create_session('test prompt', ['flux', 'gemini'])

        # Should be UUID format
        import uuid
        try:
            uuid.UUID(session_id)
            valid_uuid = True
        except ValueError:
            valid_uuid = False

        assert valid_uuid

    def test_create_session_stores_status(self, session_manager, mock_s3_client):
        """create_session() should store status.json in S3."""
        session_id = session_manager.create_session('test prompt', ['flux', 'gemini'])

        mock_s3_client.put_object.assert_called_once()
        call_args = mock_s3_client.put_object.call_args

        assert f'sessions/{session_id}/status.json' in call_args.kwargs['Key']

        # Parse and verify stored data
        stored_data = json.loads(call_args.kwargs['Body'])
        assert stored_data['prompt'] == 'test prompt'
        assert stored_data['status'] == 'pending'
        assert 'flux' in stored_data['models']
        assert 'gemini' in stored_data['models']

    def test_create_session_marks_disabled_models(self, session_manager, mock_s3_client):
        """create_session() should mark models not in enabled list as disabled."""
        session_manager.create_session('test prompt', ['flux'])

        call_args = mock_s3_client.put_object.call_args
        stored_data = json.loads(call_args.kwargs['Body'])

        assert stored_data['models']['flux']['enabled'] is True
        assert stored_data['models']['flux']['status'] == 'pending'
        assert stored_data['models']['recraft']['enabled'] is False
        assert stored_data['models']['recraft']['status'] == 'disabled'

    def test_get_session_returns_status(self, session_manager, mock_s3_client):
        """get_session() should return session status from S3."""
        session_data = {
            'sessionId': 'test-session',
            'status': 'in_progress',
            'prompt': 'test prompt',
            'models': {}
        }

        mock_s3_client.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(session_data).encode('utf-8'))
        }

        result = session_manager.get_session('test-session')

        assert result['status'] == 'in_progress'
        assert result['prompt'] == 'test prompt'

    def test_get_session_returns_none_for_missing(self, session_manager, mock_s3_client):
        """get_session() should return None for missing session."""
        from botocore.exceptions import ClientError
        mock_s3_client.get_object.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchKey'}}, 'GetObject'
        )

        result = session_manager.get_session('nonexistent')

        assert result is None

    def test_add_iteration_increments_count(self, session_manager, mock_s3_client):
        """add_iteration() should increment iteration count."""
        session_data = {
            'sessionId': 'test-session',
            'status': 'in_progress',
            'version': 1,
            'prompt': 'test prompt',
            'models': {
                'flux': {
                    'enabled': True,
                    'status': 'pending',
                    'iterationCount': 0,
                    'iterations': []
                },
                'recraft': {'enabled': False, 'status': 'disabled', 'iterationCount': 0, 'iterations': []},
                'gemini': {'enabled': False, 'status': 'disabled', 'iterationCount': 0, 'iterations': []},
                'openai': {'enabled': False, 'status': 'disabled', 'iterationCount': 0, 'iterations': []}
            }
        }

        mock_s3_client.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(session_data).encode('utf-8'))
        }

        iteration_index = session_manager.add_iteration('test-session', 'flux', 'refine prompt')

        assert iteration_index == 0

        # Verify put_object was called with updated data
        call_args = mock_s3_client.put_object.call_args
        saved_data = json.loads(call_args.kwargs['Body'])
        assert saved_data['models']['flux']['iterationCount'] == 1
        assert len(saved_data['models']['flux']['iterations']) == 1

    def test_add_iteration_rejects_at_limit(self, session_manager, mock_s3_client):
        """add_iteration() should reject when iteration limit reached."""
        session_data = {
            'sessionId': 'test-session',
            'status': 'in_progress',
            'version': 1,
            'prompt': 'test prompt',
            'models': {
                'flux': {
                    'enabled': True,
                    'status': 'completed',
                    'iterationCount': 7,  # At limit
                    'iterations': [{'index': i} for i in range(7)]
                },
                'recraft': {'enabled': False, 'status': 'disabled', 'iterationCount': 0, 'iterations': []},
                'gemini': {'enabled': False, 'status': 'disabled', 'iterationCount': 0, 'iterations': []},
                'openai': {'enabled': False, 'status': 'disabled', 'iterationCount': 0, 'iterations': []}
            }
        }

        mock_s3_client.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(session_data).encode('utf-8'))
        }

        with pytest.raises(ValueError) as excinfo:
            session_manager.add_iteration('test-session', 'flux', 'another prompt')

        assert 'limit' in str(excinfo.value).lower()

    def test_complete_iteration_stores_image_key(self, session_manager, mock_s3_client):
        """complete_iteration() should store image key and update status."""
        session_data = {
            'sessionId': 'test-session',
            'status': 'in_progress',
            'version': 1,
            'prompt': 'test prompt',
            'models': {
                'flux': {
                    'enabled': True,
                    'status': 'in_progress',
                    'iterationCount': 1,
                    'iterations': [{'index': 0, 'status': 'in_progress', 'prompt': 'test'}]
                },
                'recraft': {'enabled': False, 'status': 'disabled', 'iterationCount': 0, 'iterations': []},
                'gemini': {'enabled': False, 'status': 'disabled', 'iterationCount': 0, 'iterations': []},
                'openai': {'enabled': False, 'status': 'disabled', 'iterationCount': 0, 'iterations': []}
            }
        }

        mock_s3_client.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(session_data).encode('utf-8'))
        }

        session_manager.complete_iteration('test-session', 'flux', 0, 'image-key-123', 5.5)

        call_args = mock_s3_client.put_object.call_args
        saved_data = json.loads(call_args.kwargs['Body'])

        iteration = saved_data['models']['flux']['iterations'][0]
        assert iteration['status'] == 'completed'
        assert iteration['imageKey'] == 'image-key-123'
        assert iteration['duration'] == 5.5

    def test_fail_iteration_stores_error(self, session_manager, mock_s3_client):
        """fail_iteration() should store error message."""
        session_data = {
            'sessionId': 'test-session',
            'status': 'in_progress',
            'version': 1,
            'prompt': 'test prompt',
            'models': {
                'flux': {
                    'enabled': True,
                    'status': 'in_progress',
                    'iterationCount': 1,
                    'iterations': [{'index': 0, 'status': 'in_progress', 'prompt': 'test'}]
                },
                'recraft': {'enabled': False, 'status': 'disabled', 'iterationCount': 0, 'iterations': []},
                'gemini': {'enabled': False, 'status': 'disabled', 'iterationCount': 0, 'iterations': []},
                'openai': {'enabled': False, 'status': 'disabled', 'iterationCount': 0, 'iterations': []}
            }
        }

        mock_s3_client.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(session_data).encode('utf-8'))
        }

        session_manager.fail_iteration('test-session', 'flux', 0, 'API error')

        call_args = mock_s3_client.put_object.call_args
        saved_data = json.loads(call_args.kwargs['Body'])

        iteration = saved_data['models']['flux']['iterations'][0]
        assert iteration['status'] == 'error'
        assert iteration['error'] == 'API error'

    def test_get_iteration_count(self, session_manager, mock_s3_client):
        """get_iteration_count() should return correct count."""
        session_data = {
            'sessionId': 'test-session',
            'models': {
                'flux': {'iterationCount': 3},
            }
        }

        mock_s3_client.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(session_data).encode('utf-8'))
        }

        count = session_manager.get_iteration_count('test-session', 'flux')

        assert count == 3

    def test_get_latest_image_key(self, session_manager, mock_s3_client):
        """get_latest_image_key() should return most recent completed image key."""
        session_data = {
            'sessionId': 'test-session',
            'models': {
                'flux': {
                    'iterations': [
                        {'index': 0, 'status': 'completed', 'imageKey': 'key-0'},
                        {'index': 1, 'status': 'completed', 'imageKey': 'key-1'},
                        {'index': 2, 'status': 'in_progress'}  # No imageKey yet
                    ]
                },
            }
        }

        mock_s3_client.get_object.return_value = {
            'Body': MagicMock(read=lambda: json.dumps(session_data).encode('utf-8'))
        }

        key = session_manager.get_latest_image_key('test-session', 'flux')

        assert key == 'key-1'  # Highest index with completed status
