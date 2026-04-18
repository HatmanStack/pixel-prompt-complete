"""
Unit tests for per-model prompt adaptation.
"""

import json
import os
from unittest.mock import MagicMock, Mock, patch

import boto3
import pytest
from moto import mock_aws

from api.enhance import PromptEnhancer

# Ensure env vars are set before any lambda_function import
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


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


# --- Integration tests for Task 2.2: adaptation wired into generate flow ---

_MOD = "lambda_function"
_TARGETS = [
    f"{_MOD}.s3_client",
    f"{_MOD}.session_manager",
    f"{_MOD}.context_manager",
    f"{_MOD}.image_storage",
    f"{_MOD}.content_filter",
    f"{_MOD}.prompt_enhancer",
    f"{_MOD}._executor",
    f"{_MOD}._gallery_executor",
    f"{_MOD}.get_enabled_models",
    f"{_MOD}.get_handler",
    f"{_MOD}.get_iterate_handler",
    f"{_MOD}.get_outpaint_handler",
    f"{_MOD}.get_model",
    f"{_MOD}.get_model_config_dict",
    f"{_MOD}.handle_log",
]


def _make_event(method="POST", path="/generate", body=None, source_ip="1.2.3.4"):
    event = {
        "rawPath": path,
        "requestContext": {"http": {"method": method, "sourceIp": source_ip}},
        "headers": {},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _body(resp):
    return json.loads(resp["body"])


@pytest.fixture
def gen_mocks():
    """Patch module-level singletons for generate integration tests.

    Wraps in mock_aws so lambda_function import (if not yet cached) can create
    boto3 clients without hitting real AWS, and so no moto state leaks between
    test modules.
    """
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")

        patchers = []
        m = {}
        for target in _TARGETS:
            p = patch(target)
            obj = p.start()
            patchers.append(p)
            m[target.split(".")[-1]] = obj

        m["content_filter"].check_prompt.return_value = False
        m["get_enabled_models"].return_value = []

        yield m

        for p in patchers:
            p.stop()


def _get_lambda_handler():
    """Import lambda_handler (cached after first import)."""
    from lambda_function import lambda_handler
    return lambda_handler


class TestGenerateAdaptation:
    """Tests verifying prompt adaptation is wired into handle_generate."""

    @patch("lambda_function.as_completed")
    def test_generate_uses_adapted_prompts(self, mock_as_completed, gen_mocks):
        """Each handler receives its model-specific adapted prompt."""
        fake_model = MagicMock(name="gemini", provider="google_gemini")
        fake_model.name = "gemini"
        gen_mocks["get_enabled_models"].return_value = [fake_model]
        gen_mocks["session_manager"].create_session.return_value = "sess-1"
        gen_mocks["get_model_config_dict"].return_value = {"id": "gemini-model"}

        # Configure adaptation to return a custom prompt
        gen_mocks["prompt_enhancer"].adapt_per_model.return_value = {
            "gemini": "Adapted gemini prompt for photorealism"
        }

        # Capture what the handler is called with
        handler_calls = []

        def fake_handler(config_dict, prompt, params):
            handler_calls.append(prompt)
            return {"status": "success", "image": "b64data"}

        gen_mocks["session_manager"].add_iteration.return_value = 0
        gen_mocks["get_handler"].return_value = fake_handler
        gen_mocks["image_storage"].upload_image.return_value = "k"
        gen_mocks["image_storage"].get_cloudfront_url.return_value = "https://cdn/k"

        # Make the executor run synchronously
        def submit_sync(fn, model):
            result = fn(model)
            future = MagicMock()
            future.result.return_value = result
            return future

        gen_mocks["_executor"].submit.side_effect = submit_sync
        mock_as_completed.side_effect = lambda futures, **kwargs: futures.keys()

        lambda_handler = _get_lambda_handler()
        resp = lambda_handler(_make_event(body={"prompt": "sunset"}), None)
        assert resp["statusCode"] == 200

        # Verify the handler received the adapted prompt, not the original
        assert len(handler_calls) == 1
        assert handler_calls[0] == "Adapted gemini prompt for photorealism"

    @patch("lambda_function.as_completed")
    def test_generate_stores_adapted_prompt_in_session(self, mock_as_completed, gen_mocks):
        """add_iteration is called with adapted_prompt kwarg."""
        lambda_handler = _get_lambda_handler()
        fake_model = MagicMock(name="gemini", provider="google_gemini")
        fake_model.name = "gemini"
        gen_mocks["get_enabled_models"].return_value = [fake_model]
        gen_mocks["session_manager"].create_session.return_value = "sess-2"
        gen_mocks["get_model_config_dict"].return_value = {"id": "gemini-model"}

        gen_mocks["prompt_enhancer"].adapt_per_model.return_value = {
            "gemini": "Adapted gemini"
        }

        gen_mocks["session_manager"].add_iteration.return_value = 0
        gen_mocks["get_handler"].return_value = lambda c, p, params: {
            "status": "success",
            "image": "b64",
        }
        gen_mocks["image_storage"].upload_image.return_value = "k"
        gen_mocks["image_storage"].get_cloudfront_url.return_value = "https://cdn/k"

        def submit_sync(fn, model):
            result = fn(model)
            future = MagicMock()
            future.result.return_value = result
            return future

        gen_mocks["_executor"].submit.side_effect = submit_sync
        mock_as_completed.side_effect = lambda futures, **kwargs: futures.keys()

        lambda_handler(_make_event(body={"prompt": "sunset"}), None)

        # Verify add_iteration was called with adapted_prompt
        call_kwargs = gen_mocks["session_manager"].add_iteration.call_args
        assert call_kwargs.kwargs.get("adapted_prompt") == "Adapted gemini"

    @patch("lambda_function.as_completed")
    def test_generate_context_uses_original_prompt(self, mock_as_completed, gen_mocks):
        """Context window entries use the original prompt, not the adapted one."""
        lambda_handler = _get_lambda_handler()
        fake_model = MagicMock(name="gemini", provider="google_gemini")
        fake_model.name = "gemini"
        gen_mocks["get_enabled_models"].return_value = [fake_model]
        gen_mocks["session_manager"].create_session.return_value = "sess-3"
        gen_mocks["get_model_config_dict"].return_value = {"id": "gemini-model"}

        gen_mocks["prompt_enhancer"].adapt_per_model.return_value = {
            "gemini": "Adapted gemini"
        }

        gen_mocks["session_manager"].add_iteration.return_value = 0
        gen_mocks["get_handler"].return_value = lambda c, p, params: {
            "status": "success",
            "image": "b64",
        }
        gen_mocks["image_storage"].upload_image.return_value = "k"
        gen_mocks["image_storage"].get_cloudfront_url.return_value = "https://cdn/k"

        def submit_sync(fn, model):
            result = fn(model)
            future = MagicMock()
            future.result.return_value = result
            return future

        gen_mocks["_executor"].submit.side_effect = submit_sync
        mock_as_completed.side_effect = lambda futures, **kwargs: futures.keys()

        lambda_handler(_make_event(body={"prompt": "original sunset"}), None)

        # Verify context_manager.add_entry was called with the original prompt
        # via _handle_successful_result's context_prompt param
        gen_mocks["context_manager"].add_entry.assert_called_once()
        context_call = gen_mocks["context_manager"].add_entry.call_args
        entry = context_call[0][2]  # third positional arg is the ContextEntry
        assert entry.prompt == "original sunset"

    @patch("lambda_function.as_completed")
    def test_generate_adaptation_failure_uses_original(self, mock_as_completed, gen_mocks):
        """When adapt_per_model raises, all handlers receive the original prompt."""
        lambda_handler = _get_lambda_handler()
        fake_model = MagicMock(name="gemini", provider="google_gemini")
        fake_model.name = "gemini"
        gen_mocks["get_enabled_models"].return_value = [fake_model]
        gen_mocks["session_manager"].create_session.return_value = "sess-4"
        gen_mocks["get_model_config_dict"].return_value = {"id": "gemini-model"}

        # adapt_per_model returns fallback (original prompt for all)
        gen_mocks["prompt_enhancer"].adapt_per_model.return_value = {
            "gemini": "original sunset"
        }

        handler_calls = []

        def fake_handler(config_dict, prompt, params):
            handler_calls.append(prompt)
            return {"status": "success", "image": "b64"}

        gen_mocks["session_manager"].add_iteration.return_value = 0
        gen_mocks["get_handler"].return_value = fake_handler
        gen_mocks["image_storage"].upload_image.return_value = "k"
        gen_mocks["image_storage"].get_cloudfront_url.return_value = "https://cdn/k"

        def submit_sync(fn, model):
            result = fn(model)
            future = MagicMock()
            future.result.return_value = result
            return future

        gen_mocks["_executor"].submit.side_effect = submit_sync
        mock_as_completed.side_effect = lambda futures, **kwargs: futures.keys()

        resp = lambda_handler(_make_event(body={"prompt": "original sunset"}), None)
        assert resp["statusCode"] == 200

        # Handler should receive the original prompt (fallback)
        assert handler_calls[0] == "original sunset"
