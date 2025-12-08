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
            'FLUX_ENABLED': 'true',
            'FLUX_API_KEY': 'test-key',
            'RECRAFT_ENABLED': 'false',
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

            assert 'flux' in names
            assert 'gemini' in names
            assert 'recraft' not in names
            assert 'openai' not in names

    def test_get_model_returns_config_when_enabled(self):
        """get_model() should return config for enabled model."""
        env = {
            'FLUX_ENABLED': 'true',
            'FLUX_API_KEY': 'test-flux-key',
            'FLUX_MODEL_ID': 'flux-dev',
        }
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config
            importlib.reload(config)

            model = config.get_model('flux')
            assert model.name == 'flux'
            assert model.api_key == 'test-flux-key'
            assert model.model_id == 'flux-dev'

    def test_get_model_raises_for_disabled(self):
        """get_model() should raise ValueError for disabled model."""
        env = {
            'RECRAFT_ENABLED': 'false',
        }
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config
            importlib.reload(config)

            with pytest.raises(ValueError) as excinfo:
                config.get_model('recraft')
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

    def test_is_model_enabled(self):
        """is_model_enabled() should return correct boolean."""
        env = {
            'FLUX_ENABLED': 'true',
            'RECRAFT_ENABLED': 'false',
        }
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import config
            importlib.reload(config)

            assert config.is_model_enabled('flux') is True
            assert config.is_model_enabled('recraft') is False
            assert config.is_model_enabled('nonexistent') is False

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
            assert len(enabled) == 4

            # Default model IDs
            flux = config.MODELS['flux']
            assert flux.model_id == 'flux-pro-1.1'

    def test_iteration_limits_defined(self):
        """MAX_ITERATIONS and ITERATION_WARNING_THRESHOLD should be defined."""
        import importlib
        import config
        importlib.reload(config)

        assert hasattr(config, 'MAX_ITERATIONS')
        assert hasattr(config, 'ITERATION_WARNING_THRESHOLD')
        assert config.MAX_ITERATIONS == 7
        assert config.ITERATION_WARNING_THRESHOLD == 5
