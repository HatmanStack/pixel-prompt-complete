"""
Unit tests for per-model prompt adaptation.
"""

import json
from unittest.mock import Mock, patch

import pytest

from api.enhance import PromptEnhancer


class TestAdaptPerModel:
    """Tests for PromptEnhancer.adapt_per_model()"""

    def _make_enhancer(self, provider="openai", model_id="gpt-4o", api_key="test-key"):
        with patch("api.enhance.prompt_model_provider", provider), \
             patch("api.enhance.prompt_model_id", model_id), \
             patch("api.enhance.prompt_model_api_key", api_key):
            return PromptEnhancer()

    def test_adapt_per_model_returns_dict_for_all_models(self):
        """Mock LLM returns valid JSON with all 4 models, verify dict has all keys."""
        enhancer = self._make_enhancer()
        enabled = ["gemini", "nova", "openai", "firefly"]
        adapted = {
            "gemini": "Photorealistic sunset over mountains",
            "nova": "Artistic sunset with stylized clouds",
            "openai": "Sunset scene with precise composition",
            "firefly": "Clean commercial sunset photo",
        }

        with patch("api.enhance.get_openai_client") as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = json.dumps(adapted)
            mock_client.chat.completions.create.return_value = mock_response

            result = enhancer.adapt_per_model("sunset over mountains", enabled)

        assert set(result.keys()) == set(enabled)
        for model in enabled:
            assert isinstance(result[model], str)
            assert len(result[model]) > 0

    def test_adapt_per_model_fills_missing_models(self):
        """Mock LLM response with only 2 models, verify missing models get original prompt."""
        enhancer = self._make_enhancer()
        enabled = ["gemini", "nova", "openai", "firefly"]
        partial = {
            "gemini": "Adapted gemini prompt",
            "openai": "Adapted openai prompt",
        }

        with patch("api.enhance.get_openai_client") as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = json.dumps(partial)
            mock_client.chat.completions.create.return_value = mock_response

            result = enhancer.adapt_per_model("original prompt", enabled)

        assert result["gemini"] == "Adapted gemini prompt"
        assert result["openai"] == "Adapted openai prompt"
        assert result["nova"] == "original prompt"
        assert result["firefly"] == "original prompt"

    def test_adapt_per_model_fallback_on_invalid_json(self):
        """Mock LLM response with non-JSON text, verify all models get original prompt."""
        enhancer = self._make_enhancer()
        enabled = ["gemini", "nova"]

        with patch("api.enhance.get_openai_client") as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "This is not JSON at all"
            mock_client.chat.completions.create.return_value = mock_response

            result = enhancer.adapt_per_model("original prompt", enabled)

        assert result == {"gemini": "original prompt", "nova": "original prompt"}

    def test_adapt_per_model_fallback_on_exception(self):
        """Mock LLM client to raise, verify fallback."""
        enhancer = self._make_enhancer()
        enabled = ["gemini", "nova", "openai"]

        with patch("api.enhance.get_openai_client") as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client
            mock_client.chat.completions.create.side_effect = Exception("API Error")

            result = enhancer.adapt_per_model("original prompt", enabled)

        assert result == {m: "original prompt" for m in enabled}

    def test_adapt_per_model_no_llm_configured(self):
        """Create enhancer with no prompt model, verify all models get original prompt."""
        enhancer = self._make_enhancer(provider="", model_id="", api_key="")

        result = enhancer.adapt_per_model("original prompt", ["gemini", "nova"])

        assert result == {"gemini": "original prompt", "nova": "original prompt"}

    def test_adapt_per_model_only_enabled_models(self):
        """Pass 2 enabled models, verify only those appear in result."""
        enhancer = self._make_enhancer()
        enabled = ["gemini", "firefly"]
        adapted = {
            "gemini": "Adapted gemini",
            "firefly": "Adapted firefly",
            "openai": "Should not appear",
        }

        with patch("api.enhance.get_openai_client") as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = json.dumps(adapted)
            mock_client.chat.completions.create.return_value = mock_response

            result = enhancer.adapt_per_model("test prompt", enabled)

        assert set(result.keys()) == {"gemini", "firefly"}
        assert result["gemini"] == "Adapted gemini"
        assert result["firefly"] == "Adapted firefly"

    def test_adapt_per_model_gemini_provider(self):
        """Test adaptation using Gemini provider."""
        enhancer = self._make_enhancer(provider="google_gemini", model_id="gemini-2.0-flash-exp")
        enabled = ["gemini", "nova"]
        adapted = {"gemini": "Gemini adapted", "nova": "Nova adapted"}

        with patch("api.enhance.get_genai_client") as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client
            mock_response = Mock()
            mock_candidate = Mock()
            mock_part = Mock()
            mock_part.text = json.dumps(adapted)
            mock_candidate.content.parts = [mock_part]
            mock_response.candidates = [mock_candidate]
            mock_client.models.generate_content.return_value = mock_response

            result = enhancer.adapt_per_model("test prompt", enabled)

        assert result["gemini"] == "Gemini adapted"
        assert result["nova"] == "Nova adapted"

    def test_adapt_per_model_openai_uses_json_mode(self):
        """Test that OpenAI provider uses response_format for GPT-4+ models."""
        enhancer = self._make_enhancer(provider="openai", model_id="gpt-4o")
        enabled = ["gemini"]
        adapted = {"gemini": "Adapted"}

        with patch("api.enhance.get_openai_client") as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = json.dumps(adapted)
            mock_client.chat.completions.create.return_value = mock_response

            enhancer.adapt_per_model("test", enabled)

            call_args = mock_client.chat.completions.create.call_args
            assert call_args.kwargs.get("response_format") == {"type": "json_object"}
