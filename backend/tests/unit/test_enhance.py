"""
Unit tests for prompt enhancement API
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.api.enhance import PromptEnhancer


class TestPromptEnhancer:
    """Tests for PromptEnhancer class"""

    def test_enhance_with_openai_provider(self):
        """Test prompt enhancement using OpenAI provider"""
        # Mock model registry
        mock_registry = Mock()
        mock_registry.get_prompt_model.return_value = {
            'name': 'GPT-4o Mini',
            'provider': 'openai',
            'key': 'test-openai-key'
        }

        enhancer = PromptEnhancer(mock_registry)

        # Mock OpenAI client
        with patch('src.api.enhance.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            # Mock completion response
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "A majestic orange tabby cat with striking green eyes"
            mock_client.chat.completions.create.return_value = mock_response

            result = enhancer.enhance("cat")

            assert result == "A majestic orange tabby cat with striking green eyes"
            mock_client.chat.completions.create.assert_called_once()

            # Verify correct model was used
            call_args = mock_client.chat.completions.create.call_args
            assert call_args.kwargs['model'] == 'gpt-4o-mini'

    def test_enhance_with_google_gemini_provider(self):
        """Test prompt enhancement using Google Gemini provider"""
        # Mock model registry
        mock_registry = Mock()
        mock_registry.get_prompt_model.return_value = {
            'name': 'Gemini 2.0 Flash',
            'provider': 'google_gemini',
            'key': 'test-gemini-key'
        }

        enhancer = PromptEnhancer(mock_registry)

        # Mock Google genai client
        with patch('src.api.enhance.genai.Client') as mock_genai_client:
            mock_client = Mock()
            mock_genai_client.return_value = mock_client

            # Mock Gemini response structure
            mock_response = Mock()
            mock_candidate = Mock()
            mock_part = Mock()
            mock_part.text = "A breathtaking sunset over a calm ocean with vibrant colors"
            mock_candidate.content.parts = [mock_part]
            mock_response.candidates = [mock_candidate]

            mock_client.models.generate_content.return_value = mock_response

            result = enhancer.enhance("sunset")

            assert result == "A breathtaking sunset over a calm ocean with vibrant colors"
            mock_client.models.generate_content.assert_called_once()

    def test_enhance_with_custom_base_url(self):
        """Test enhancement with OpenAI-compatible provider using custom base_url"""
        # Mock model registry
        mock_registry = Mock()
        mock_registry.get_prompt_model.return_value = {
            'name': 'Custom Model',
            'provider': 'openai_compatible',
            'key': 'test-key',
            'base_url': 'https://custom-api.example.com/v1'
        }

        enhancer = PromptEnhancer(mock_registry)

        with patch('src.api.enhance.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "Enhanced prompt text"
            mock_client.chat.completions.create.return_value = mock_response

            result = enhancer.enhance("test")

            # Verify custom base_url was passed
            call_args = mock_openai.call_args
            assert call_args.kwargs['base_url'] == 'https://custom-api.example.com/v1'
            assert result == "Enhanced prompt text"

    def test_enhance_returns_original_on_error(self):
        """Test that enhance returns original prompt if enhancement fails"""
        mock_registry = Mock()
        mock_registry.get_prompt_model.return_value = {
            'name': 'GPT-4o Mini',
            'provider': 'openai',
            'key': 'test-key'
        }

        enhancer = PromptEnhancer(mock_registry)

        with patch('src.api.enhance.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            # Simulate API error
            mock_client.chat.completions.create.side_effect = Exception("API Error")

            result = enhancer.enhance("original prompt")

            # Should return original prompt on error
            assert result == "original prompt"

    def test_enhance_with_no_prompt_model(self):
        """Test enhancement when no prompt model is configured"""
        mock_registry = Mock()
        mock_registry.get_prompt_model.return_value = None

        enhancer = PromptEnhancer(mock_registry)

        result = enhancer.enhance("test prompt")

        # Should return original prompt
        assert result == "test prompt"

    def test_enhance_with_empty_prompt(self):
        """Test enhancement with empty prompt"""
        mock_registry = Mock()

        enhancer = PromptEnhancer(mock_registry)

        assert enhancer.enhance("") is None
        assert enhancer.enhance(None) is None

    def test_enhance_safe_never_returns_none(self):
        """Test that enhance_safe always returns a string"""
        mock_registry = Mock()
        mock_registry.get_prompt_model.return_value = None

        enhancer = PromptEnhancer(mock_registry)

        # With valid prompt
        result = enhancer.enhance_safe("test")
        assert result == "test"
        assert result is not None

        # With empty prompt
        result = enhancer.enhance_safe("")
        assert result == ""
        assert result is not None

    def test_enhance_safe_returns_enhanced_when_successful(self):
        """Test that enhance_safe returns enhanced prompt on success"""
        mock_registry = Mock()
        mock_registry.get_prompt_model.return_value = {
            'name': 'GPT-4o Mini',
            'provider': 'openai',
            'key': 'test-key'
        }

        enhancer = PromptEnhancer(mock_registry)

        with patch('src.api.enhance.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "Enhanced version"
            mock_client.chat.completions.create.return_value = mock_response

            result = enhancer.enhance_safe("short")

            assert result == "Enhanced version"

    def test_enhance_with_gemini_empty_candidates(self):
        """Test handling of empty candidates from Gemini"""
        mock_registry = Mock()
        mock_registry.get_prompt_model.return_value = {
            'name': 'Gemini 2.0 Flash',
            'provider': 'google_gemini',
            'key': 'test-key'
        }

        enhancer = PromptEnhancer(mock_registry)

        with patch('src.api.enhance.genai.Client') as mock_genai_client:
            mock_client = Mock()
            mock_genai_client.return_value = mock_client

            # Mock empty candidates response
            mock_response = Mock()
            mock_response.candidates = []

            mock_client.models.generate_content.return_value = mock_response

            result = enhancer.enhance("test")

            # Should return original prompt on error
            assert result == "test"

    def test_enhance_includes_system_prompt(self):
        """Test that enhancement includes the system prompt"""
        mock_registry = Mock()
        mock_registry.get_prompt_model.return_value = {
            'name': 'GPT-4o Mini',
            'provider': 'openai',
            'key': 'test-key'
        }

        enhancer = PromptEnhancer(mock_registry)

        with patch('src.api.enhance.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "Enhanced"
            mock_client.chat.completions.create.return_value = mock_response

            enhancer.enhance("test")

            # Verify messages structure
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs['messages']

            assert len(messages) == 2
            assert messages[0]['role'] == 'system'
            assert messages[1]['role'] == 'user'
            assert messages[1]['content'] == 'test'

    def test_enhance_uses_correct_parameters(self):
        """Test that enhancement uses correct API parameters"""
        mock_registry = Mock()
        mock_registry.get_prompt_model.return_value = {
            'name': 'GPT-4o Mini',
            'provider': 'openai',
            'key': 'test-key'
        }

        enhancer = PromptEnhancer(mock_registry)

        with patch('src.api.enhance.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "Enhanced"
            mock_client.chat.completions.create.return_value = mock_response

            enhancer.enhance("test")

            call_args = mock_client.chat.completions.create.call_args
            assert call_args.kwargs['max_tokens'] == 200
            assert call_args.kwargs['temperature'] == 0.7

    def test_enhance_strips_whitespace_from_response(self):
        """Test that enhanced prompts have whitespace stripped"""
        mock_registry = Mock()
        mock_registry.get_prompt_model.return_value = {
            'name': 'GPT-4o Mini',
            'provider': 'openai',
            'key': 'test-key'
        }

        enhancer = PromptEnhancer(mock_registry)

        with patch('src.api.enhance.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client

            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "\n\n  Enhanced prompt with whitespace  \n\n"
            mock_client.chat.completions.create.return_value = mock_response

            result = enhancer.enhance("test")

            assert result == "Enhanced prompt with whitespace"
