"""
Prompt Enhancement module for Pixel Prompt Complete.

Uses configured LLM to expand short prompts into detailed image generation prompts.
Includes per-model prompt adaptation for tailored image generation.
"""

import json
import warnings
from typing import Any, Optional

from config import prompt_model_api_key, prompt_model_id, prompt_model_provider
from utils.clients import get_genai_client, get_openai_client
from utils.logger import StructuredLogger

# Per-model parameter configuration. First match wins.
_MODEL_PARAMS: dict[str, dict[str, Any]] = {
    "gpt-5": {"max_completion_tokens": 1000},
    "gpt-4o": {"max_completion_tokens": 200, "temperature": 0.7},
}
_DEFAULT_PARAMS: dict[str, Any] = {"max_tokens": 200, "temperature": 0.7}


def _get_model_params(model_id: str) -> dict[str, Any]:
    """Return model-specific completion params for the given model ID."""
    for key, params in _MODEL_PARAMS.items():
        if key in model_id:
            return dict(params)
    return dict(_DEFAULT_PARAMS)


class PromptEnhancer:
    """
    Enhances short prompts into detailed image generation prompts using LLM.
    """

    def __init__(self):
        """Initialize Prompt Enhancer from config module settings."""
        # Build prompt model config from config.py values
        if prompt_model_provider and prompt_model_id:
            self.prompt_model = {
                "provider": prompt_model_provider,
                "id": prompt_model_id,
            }
            if prompt_model_api_key:
                self.prompt_model["api_key"] = prompt_model_api_key
        else:
            self.prompt_model = None

        # System prompt for prompt enhancement
        self.system_prompt = """You are an expert at creating detailed, vivid image generation prompts.

Your task is to take a short, simple prompt and expand it into a rich, detailed prompt that will produce better AI-generated images.

Guidelines:
- Add specific details about composition, lighting, style, and mood
- Include artistic references or styles when appropriate
- Keep the core concept from the original prompt
- Make it descriptive but not overly long (2-4 sentences ideal)
- Focus on visual details that AI image generators can understand
- Use adjectives that describe visual qualities

Example transformations:
- "cat" → "A photorealistic portrait of a fluffy orange tabby cat with striking green eyes, sitting on a windowsill bathed in warm afternoon sunlight, shot with shallow depth of field"
- "sunset" → "A breathtaking sunset over a calm ocean, with vibrant orange and purple hues reflecting on the water, dramatic cloud formations, cinematic composition with silhouetted palm trees in the foreground"

Enhance the following prompt:"""

        # System prompt for per-model prompt adaptation
        self.adaptation_system_prompt = (
            "You are an expert at optimizing image generation prompts for specific AI models.\n"
            "Given a user's prompt, produce a JSON object with model-specific variants.\n"
            "Keys must match exactly: {model_keys}.\n"
            "Each variant should be 2-4 sentences tailored to the model's strengths:\n"
            "- gemini: strong at photorealism, natural scenes, complex multi-element compositions\n"
            "- nova: artistic styles, illustrations, stylized imagery\n"
            "- openai: precise composition, typography, literal interpretation of instructions\n"
            "- firefly: clean commercial imagery, product photography, design assets\n"
            "Keep the core intent identical across all variants.\n"
            "Return ONLY valid JSON. No markdown, no explanation."
        )

    def adapt_per_model(self, prompt: str, enabled_models: list[str]) -> dict[str, str]:
        """Adapt a prompt for each enabled model's strengths via a single LLM call.

        Args:
            prompt: The user's original prompt.
            enabled_models: List of enabled model names (e.g. ["gemini", "nova"]).

        Returns:
            Dict mapping model name to adapted prompt string.
            Falls back to original prompt for all models on any failure.
        """
        fallback = {m: prompt for m in enabled_models}

        if not self.prompt_model:
            return fallback

        try:
            provider = self.prompt_model["provider"]
            api_key = self.prompt_model.get("api_key", "")
            if not api_key:
                return fallback

            model_keys = ", ".join(enabled_models)
            system_prompt = self.adaptation_system_prompt.format(model_keys=model_keys)

            if provider == "google_gemini":
                client = get_genai_client(api_key)
                generation_config: dict[str, Any] = {
                    "response_mime_type": "application/json",
                }
                response = client.models.generate_content(
                    model=self.prompt_model["id"],
                    contents=f"{system_prompt}\n\n{prompt}",
                    config=generation_config,
                )
                if not response.candidates or len(response.candidates) == 0:
                    raise ValueError("Gemini returned empty candidates")
                response_text = response.candidates[0].content.parts[0].text.strip()
            else:
                client_kwargs: dict[str, Any] = {"timeout": 10.0}
                if "base_url" in self.prompt_model:
                    client_kwargs["base_url"] = self.prompt_model["base_url"]
                client = get_openai_client(api_key, **client_kwargs)

                completion_params: dict[str, Any] = {
                    "model": self.prompt_model["id"],
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 1000,
                    "temperature": 0.7,
                    "timeout": 10.0,
                }
                model_id = self.prompt_model["id"]
                if "gpt-4" in model_id or "gpt-5" in model_id:
                    completion_params["response_format"] = {"type": "json_object"}

                response = client.chat.completions.create(**completion_params)
                response_text = response.choices[0].message.content
                if response_text:
                    response_text = response_text.strip()
                else:
                    raise ValueError("Empty response from LLM")

            parsed = json.loads(response_text)
            if not isinstance(parsed, dict):
                raise ValueError("LLM response is not a JSON object")

            # Build result: use adapted prompt if available, otherwise original
            result = {}
            for model in enabled_models:
                value = parsed.get(model)
                if isinstance(value, str) and value.strip():
                    result[model] = value
                else:
                    result[model] = prompt

            return result

        except Exception as e:
            StructuredLogger.warning(f"Prompt adaptation failed: {e}")
            return fallback

    def enhance(self, prompt: str) -> Optional[str]:
        """
        Enhance a short prompt into a detailed one.

        Args:
            prompt: Short prompt to enhance

        Returns:
            Enhanced prompt string or None if enhancement fails
        """
        if not prompt:
            return None

        prompt_model = self.prompt_model

        if not prompt_model:
            return prompt

        try:
            provider = prompt_model["provider"]

            # Branch based on provider type
            if provider == "google_gemini":
                # Use Google genai client for Gemini
                api_key = prompt_model.get("api_key", "")
                if not api_key:
                    return prompt

                client = get_genai_client(api_key)

                response = client.models.generate_content(
                    model=prompt_model["id"], contents=f"{self.system_prompt}\n\n{prompt}"
                )

                # Extract text from Gemini response
                if not response.candidates or len(response.candidates) == 0:
                    raise ValueError("Gemini returned empty candidates")

                enhanced = response.candidates[0].content.parts[0].text.strip()

            else:
                # Use OpenAI client for OpenAI and OpenAI-compatible providers
                api_key = prompt_model.get("api_key", "")
                if not api_key:
                    return prompt

                client_kwargs = {"timeout": 30.0}

                # Support custom base_url for OpenAI-compatible providers
                if "base_url" in prompt_model:
                    client_kwargs["base_url"] = prompt_model["base_url"]

                client = get_openai_client(api_key, **client_kwargs)

                # Determine model identifier from prompt_model
                model_id = prompt_model["id"]

                completion_params: dict[str, Any] = {
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    **_get_model_params(model_id),
                }

                response = client.chat.completions.create(**completion_params)

                # Extract enhanced prompt
                enhanced = response.choices[0].message.content
                if enhanced:
                    enhanced = enhanced.strip()
                else:
                    enhanced = ""

            return enhanced

        except Exception as e:
            # Return original prompt on error, but warn about failure
            warnings.warn(f"Prompt enhancement failed: {e}")
            return prompt

    def enhance_safe(self, prompt: str) -> str:
        """
        Enhance prompt with guaranteed return (never returns None).

        Args:
            prompt: Short prompt to enhance

        Returns:
            Enhanced prompt or original prompt if enhancement fails
        """
        enhanced = self.enhance(prompt)
        return enhanced if enhanced else prompt
