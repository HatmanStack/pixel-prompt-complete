"""
Unit tests for logging endpoint.
"""

import pytest
from unittest.mock import MagicMock, patch
from src.api.log import handle_log


def test_handle_log_success():
    """Test successful log handling."""
    body = {
        'level': 'ERROR',
        'message': 'Test error message',
        'stack': 'Error: test\n  at line 1',
        'metadata': {'component': 'TestComponent'}
    }

    with patch('src.api.log.StructuredLogger.log') as mock_log:
        result = handle_log(body, 'test-correlation-123', '192.168.1.1')

        assert result['success'] is True
        assert result['message'] == 'Log received successfully'

        # Verify logger was called with correct parameters
        mock_log.assert_called_once()
        call_args = mock_log.call_args

        assert call_args[1]['level'] == 'ERROR'
        assert call_args[1]['message'] == 'Test error message'
        assert call_args[1]['correlation_id'] == 'test-correlation-123'
        assert 'stack' in call_args[1]
        assert call_args[1]['stack'] == 'Error: test\n  at line 1'
        assert call_args[1]['component'] == 'TestComponent'
        assert call_args[1]['ip'] == '192.168.1.1'


def test_handle_log_missing_level():
    """Test log handling with missing level field."""
    body = {
        'message': 'Test error message'
    }

    with pytest.raises(ValueError, match="Field 'level' is required"):
        handle_log(body, 'test-correlation-123', '192.168.1.1')


def test_handle_log_missing_message():
    """Test log handling with missing message field."""
    body = {
        'level': 'ERROR'
    }

    with pytest.raises(ValueError, match="Field 'message' is required"):
        handle_log(body, 'test-correlation-123', '192.168.1.1')


def test_handle_log_invalid_level():
    """Test log handling with invalid log level."""
    body = {
        'level': 'INVALID',
        'message': 'Test message'
    }

    with pytest.raises(ValueError, match="Invalid log level"):
        handle_log(body, 'test-correlation-123', '192.168.1.1')


def test_handle_log_valid_levels():
    """Test all valid log levels."""
    valid_levels = ['ERROR', 'WARNING', 'INFO', 'DEBUG']

    with patch('src.api.log.StructuredLogger.log') as mock_log:
        for level in valid_levels:
            body = {
                'level': level,
                'message': f'Test {level} message'
            }

            result = handle_log(body, 'test-123', '192.168.1.1')
            assert result['success'] is True

            # Verify logger was called with correct level
            call_args = mock_log.call_args
            assert call_args[1]['level'] == level


def test_handle_log_case_insensitive_level():
    """Test log level handling is case-insensitive."""
    body = {
        'level': 'error',  # lowercase
        'message': 'Test message'
    }

    with patch('src.api.log.StructuredLogger.log') as mock_log:
        result = handle_log(body, 'test-123', '192.168.1.1')

        assert result['success'] is True

        # Verify level was converted to uppercase
        call_args = mock_log.call_args
        assert call_args[1]['level'] == 'ERROR'


def test_handle_log_without_stack():
    """Test log handling without stack trace."""
    body = {
        'level': 'ERROR',
        'message': 'Test error message'
    }

    with patch('src.api.log.StructuredLogger.log') as mock_log:
        result = handle_log(body, 'test-123', '192.168.1.1')

        assert result['success'] is True

        # Verify stack is not in call args
        call_args = mock_log.call_args
        assert 'stack' not in call_args[1]


def test_handle_log_without_correlation_id():
    """Test log handling without correlation ID."""
    body = {
        'level': 'ERROR',
        'message': 'Test error message'
    }

    with patch('src.api.log.StructuredLogger.log') as mock_log:
        result = handle_log(body, None, '192.168.1.1')

        assert result['success'] is True

        # Verify correlation_id is None
        call_args = mock_log.call_args
        assert call_args[1]['correlation_id'] is None


def test_handle_log_with_custom_metadata():
    """Test log handling with custom metadata."""
    body = {
        'level': 'ERROR',
        'message': 'Test error message',
        'metadata': {
            'component': 'ErrorBoundary',
            'action': 'render',
            'userAgent': 'Mozilla/5.0'
        }
    }

    with patch('src.api.log.StructuredLogger.log') as mock_log:
        result = handle_log(body, 'test-123', '192.168.1.1')

        assert result['success'] is True

        # Verify all metadata fields are passed
        call_args = mock_log.call_args
        assert call_args[1]['component'] == 'ErrorBoundary'
        assert call_args[1]['action'] == 'render'
        assert call_args[1]['userAgent'] == 'Mozilla/5.0'
        assert call_args[1]['ip'] == '192.168.1.1'
