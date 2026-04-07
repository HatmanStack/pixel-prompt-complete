"""
Unit tests for the v2 configuration module.
"""

import os
import pytest
from unittest.mock import patch


class TestModelConfig:
    """Tests for ModelConfig dataclass and model loading."""

    def test_get_enabled_models_returns_enabled_only(self):
        """Only enabled models should be returned."""
        env = {
            'GEMINI_ENABLED': 'true',
            'GEMINI_API_KEY': 'test-key-2',
            'OPENAI_ENABLED': 'false',
        }
        with patch.dict(os.environ, env, clear=True):
            # Re-import to pick up env
            import importlib
            import config
            importlib.reload(config)

            enabled = config.get_enabled_models()
            names = [m.name for m in enabled]

            assert 'gemini' in names
            assert 'openai' not in names

    def test_get_model_returns_config_when_enabled(self):
        """get_model() should return config for enabled model."""
        env = {
            'GEMINI_ENABLED': 'true',
            'GEMINI_API_KEY': 'test-gemini-key',
            'GEMINI_MODEL_ID': 'gemini-test',
        }
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config
            importlib.reload(config)

            model = config.get_model('gemini')
            assert model.name == 'gemini'
            assert model.api_key == 'test-gemini-key'
            assert model.model_id == 'gemini-test'

    def test_get_model_raises_for_disabled(self):
        """get_model() should raise ValueError for disabled model."""
        env = {
            'OPENAI_ENABLED': 'false',
        }
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config
            importlib.reload(config)

            with pytest.raises(ValueError) as excinfo:
                config.get_model('openai')
            assert 'disabled' in str(excinfo.value).lower()

    def test_get_model_raises_for_unknown(self):
        """get_model() should raise ValueError for unknown model name."""
        env = {}
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config
            importlib.reload(config)

            with pytest.raises(ValueError) as excinfo:
                config.get_model('unknown_model')
            assert 'unknown model' in str(excinfo.value).lower()

    def test_get_model_config_dict(self):
        """get_model_config_dict() should return handler-compatible dict."""
        env = {
            'GEMINI_ENABLED': 'true',
            'GEMINI_API_KEY': 'test-gemini-key',
            'GEMINI_MODEL_ID': 'gemini-2.0-flash',
        }
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config
            importlib.reload(config)

            model = config.get_model('gemini')
            config_dict = config.get_model_config_dict(model)

            assert config_dict['id'] == 'gemini-2.0-flash'
            assert config_dict['api_key'] == 'test-gemini-key'
            assert config_dict['provider'] == 'google_gemini'

    def test_default_values_when_env_missing(self):
        """Default values should be used when env vars missing."""
        env = {}
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config
            importlib.reload(config)

            # All models default to enabled=True
            enabled = config.get_enabled_models()
            assert len(enabled) == 2  # gemini, openai

    def test_iteration_limits_defined(self):
        """MAX_ITERATIONS and ITERATION_WARNING_THRESHOLD should be defined."""
        import importlib
        import config
        importlib.reload(config)

        assert hasattr(config, 'MAX_ITERATIONS')
        assert hasattr(config, 'ITERATION_WARNING_THRESHOLD')
        assert config.MAX_ITERATIONS == 7
        assert config.ITERATION_WARNING_THRESHOLD == 5
