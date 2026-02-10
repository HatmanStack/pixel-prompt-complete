"""
Unit tests for prompt enhancement API
"""

from unittest.mock import Mock, patch

from api.enhance import PromptEnhancer


class TestPromptEnhancer:
    """Tests for PromptEnhancer class"""

    def test_enhance_with_openai_provider(self):
        """Test prompt enhancement using OpenAI provider"""
        with patch('api.enhance.prompt_model_provider', 'openai'), \
             patch('api.enhance.prompt_model_id', 'gpt-4o-mini'), \
             patch('api.enhance.prompt_model_api_key', 'test-openai-key'):

            enhancer = PromptEnhancer()

            with patch('api.enhance.OpenAI') as mock_openai:
                mock_client = Mock()
                mock_openai.return_value = mock_client

                mock_response = Mock()
                mock_response.choices = [Mock()]
                mock_response.choices[0].message.content = "A majestic orange tabby cat with striking green eyes"
                mock_client.chat.completions.create.return_value = mock_response

                result = enhancer.enhance("cat")

                assert result == "A majestic orange tabby cat with striking green eyes"
                mock_client.chat.completions.create.assert_called_once()

                call_args = mock_client.chat.completions.create.call_args
                assert call_args.kwargs['model'] == 'gpt-4o-mini'

    def test_enhance_with_google_gemini_provider(self):
        """Test prompt enhancement using Google Gemini provider"""
        with patch('api.enhance.prompt_model_provider', 'google_gemini'), \
             patch('api.enhance.prompt_model_id', 'gemini-2.0-flash-exp'), \
             patch('api.enhance.prompt_model_api_key', 'test-gemini-key'):

            enhancer = PromptEnhancer()

            with patch('api.enhance.genai.Client') as mock_genai_client:
                mock_client = Mock()
                mock_genai_client.return_value = mock_client

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
        with patch('api.enhance.prompt_model_provider', 'generic'), \
             patch('api.enhance.prompt_model_id', 'custom-model'), \
             patch('api.enhance.prompt_model_api_key', 'test-key'):

            enhancer = PromptEnhancer()
            # Manually add base_url for testing
            enhancer.prompt_model['base_url'] = 'https://custom-api.example.com/v1'

            with patch('api.enhance.OpenAI') as mock_openai:
                mock_client = Mock()
                mock_openai.return_value = mock_client

                mock_response = Mock()
                mock_response.choices = [Mock()]
                mock_response.choices[0].message.content = "Enhanced prompt text"
                mock_client.chat.completions.create.return_value = mock_response

                result = enhancer.enhance("test")

                call_args = mock_openai.call_args
                assert call_args.kwargs['base_url'] == 'https://custom-api.example.com/v1'
                assert result == "Enhanced prompt text"

    def test_enhance_returns_original_on_error(self):
        """Test that enhance returns original prompt if enhancement fails"""
        with patch('api.enhance.prompt_model_provider', 'openai'), \
             patch('api.enhance.prompt_model_id', 'gpt-4o-mini'), \
             patch('api.enhance.prompt_model_api_key', 'test-key'):

            enhancer = PromptEnhancer()

            with patch('api.enhance.OpenAI') as mock_openai:
                mock_client = Mock()
                mock_openai.return_value = mock_client

                mock_client.chat.completions.create.side_effect = Exception("API Error")

                result = enhancer.enhance("original prompt")

                assert result == "original prompt"

    def test_enhance_with_no_prompt_model(self):
        """Test enhancement when no prompt model is configured"""
        with patch('api.enhance.prompt_model_provider', ''), \
             patch('api.enhance.prompt_model_id', ''), \
             patch('api.enhance.prompt_model_api_key', ''):

            enhancer = PromptEnhancer()

            result = enhancer.enhance("test prompt")

            assert result == "test prompt"

    def test_enhance_with_empty_prompt(self):
        """Test enhancement with empty prompt"""
        with patch('api.enhance.prompt_model_provider', ''), \
             patch('api.enhance.prompt_model_id', ''), \
             patch('api.enhance.prompt_model_api_key', ''):

            enhancer = PromptEnhancer()

            assert enhancer.enhance("") is None
            assert enhancer.enhance(None) is None

    def test_enhance_safe_never_returns_none(self):
        """Test that enhance_safe always returns a string"""
        with patch('api.enhance.prompt_model_provider', ''), \
             patch('api.enhance.prompt_model_id', ''), \
             patch('api.enhance.prompt_model_api_key', ''):

            enhancer = PromptEnhancer()

            result = enhancer.enhance_safe("test")
            assert result == "test"
            assert result is not None

            result = enhancer.enhance_safe("")
            assert result == ""
            assert result is not None

    def test_enhance_safe_returns_enhanced_when_successful(self):
        """Test that enhance_safe returns enhanced prompt on success"""
        with patch('api.enhance.prompt_model_provider', 'openai'), \
             patch('api.enhance.prompt_model_id', 'gpt-4o-mini'), \
             patch('api.enhance.prompt_model_api_key', 'test-key'):

            enhancer = PromptEnhancer()

            with patch('api.enhance.OpenAI') as mock_openai:
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
        with patch('api.enhance.prompt_model_provider', 'google_gemini'), \
             patch('api.enhance.prompt_model_id', 'gemini-2.0-flash-exp'), \
             patch('api.enhance.prompt_model_api_key', 'test-key'):

            enhancer = PromptEnhancer()

            with patch('api.enhance.genai.Client') as mock_genai_client:
                mock_client = Mock()
                mock_genai_client.return_value = mock_client

                mock_response = Mock()
                mock_response.candidates = []

                mock_client.models.generate_content.return_value = mock_response

                result = enhancer.enhance("test")

                assert result == "test"

    def test_enhance_includes_system_prompt(self):
        """Test that enhancement includes the system prompt"""
        with patch('api.enhance.prompt_model_provider', 'openai'), \
             patch('api.enhance.prompt_model_id', 'gpt-4o-mini'), \
             patch('api.enhance.prompt_model_api_key', 'test-key'):

            enhancer = PromptEnhancer()

            with patch('api.enhance.OpenAI') as mock_openai:
                mock_client = Mock()
                mock_openai.return_value = mock_client

                mock_response = Mock()
                mock_response.choices = [Mock()]
                mock_response.choices[0].message.content = "Enhanced"
                mock_client.chat.completions.create.return_value = mock_response

                enhancer.enhance("test")

                call_args = mock_client.chat.completions.create.call_args
                messages = call_args.kwargs['messages']

                assert len(messages) == 2
                assert messages[0]['role'] == 'system'
                assert messages[1]['role'] == 'user'
                assert messages[1]['content'] == 'test'

    def test_enhance_uses_correct_parameters(self):
        """Test that enhancement uses correct API parameters"""
        with patch('api.enhance.prompt_model_provider', 'openai'), \
             patch('api.enhance.prompt_model_id', 'gpt-4o-mini'), \
             patch('api.enhance.prompt_model_api_key', 'test-key'):

            enhancer = PromptEnhancer()

            with patch('api.enhance.OpenAI') as mock_openai:
                mock_client = Mock()
                mock_openai.return_value = mock_client

                mock_response = Mock()
                mock_response.choices = [Mock()]
                mock_response.choices[0].message.content = "Enhanced"
                mock_client.chat.completions.create.return_value = mock_response

                enhancer.enhance("test")

                call_args = mock_client.chat.completions.create.call_args
                # gpt-4o-mini matches "gpt-4o" branch -> max_completion_tokens
                assert call_args.kwargs['max_completion_tokens'] == 200
                assert call_args.kwargs['temperature'] == 0.7

    def test_enhance_strips_whitespace_from_response(self):
        """Test that enhanced prompts have whitespace stripped"""
        with patch('api.enhance.prompt_model_provider', 'openai'), \
             patch('api.enhance.prompt_model_id', 'gpt-4o-mini'), \
             patch('api.enhance.prompt_model_api_key', 'test-key'):

            enhancer = PromptEnhancer()

            with patch('api.enhance.OpenAI') as mock_openai:
                mock_client = Mock()
                mock_openai.return_value = mock_client

                mock_response = Mock()
                mock_response.choices = [Mock()]
                mock_response.choices[0].message.content = "\n\n  Enhanced prompt with whitespace  \n\n"
                mock_client.chat.completions.create.return_value = mock_response

                result = enhancer.enhance("test")

                assert result == "Enhanced prompt with whitespace"
