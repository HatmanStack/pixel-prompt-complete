"""
Prompt Enhancement module for Pixel Prompt Complete.

Uses configured LLM to expand short prompts into detailed image generation prompts.
Includes per-model prompt adaptation for tailored image generation.
"""

import json
from typing import Any, Optional

from config import enhance_timeout, prompt_model_api_key, prompt_model_id, prompt_model_provider
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

    @property
    def is_available(self) -> bool:
        """True when a real LLM call will actually be made.

        Both ``enhance`` and ``adapt_per_model`` short-circuit to the original
        prompt when no provider or no API key is configured — a supported
        setup, since open-source mode ships without PROMPT_MODEL_API_KEY.
        Callers that meter cost must consult this, or they book spend for a
        call that never happened, corrupting the very numbers the meter
        exists to produce.
        """
        return bool(self.prompt_model and self.prompt_model.get("api_key"))

    def adapt_per_model(
        self,
        prompt: str,
        enabled_models: list[str],
        correlation_id: str | None = None,
    ) -> dict[str, str]:
        """Adapt a single user prompt into model-specific prompts via one LLM call.

        Uses a single LLM call with a JSON response to produce per-model adapted
        prompts instead of making N separate calls.  This reduces latency and
        cost by ~4x compared to individual adaptation calls.

        Args:
            prompt: The user's original prompt.
            enabled_models: List of enabled model names (e.g. ["gemini", "nova"]).
            correlation_id: Optional request correlation ID for structured logging.

        Returns:
            Dict mapping model name to adapted prompt string.
            Falls back to original prompt for all models on any failure.
        """
        fallback = {m: prompt for m in enabled_models}

        if not self.is_available:
            return fallback

        try:
            assert self.prompt_model is not None  # guaranteed by is_available
            provider = self.prompt_model["provider"]
            api_key = self.prompt_model["api_key"]

            model_keys = ", ".join(enabled_models)
            system_prompt = self.adaptation_system_prompt.format(model_keys=model_keys)

            if provider == "google_gemini":
                client = get_genai_client(api_key, timeout=enhance_timeout)
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
                client_kwargs: dict[str, Any] = {"timeout": enhance_timeout}
                if "base_url" in self.prompt_model:
                    client_kwargs["base_url"] = self.prompt_model["base_url"]
                client = get_openai_client(api_key, **client_kwargs)

                model_id = self.prompt_model["id"]
                completion_params: dict[str, Any] = {
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    **_get_model_params(model_id),
                }
                # The base_url guard matches _complete's, and for the same
                # reason: a custom base_url means an OpenAI-compatible third
                # party, and many of those reject response_format outright.
                # Keying only on the model id meant a third-party endpoint
                # serving a "gpt-4"- or "gpt-5"-named model raised here, and
                # the except below silently fell back to the original prompt
                # for EVERY model -- disabling per-model adaptation entirely
                # with nothing louder than a warning to show for it.
                if ("gpt-4" in model_id or "gpt-5" in model_id) and (
                    "base_url" not in self.prompt_model
                ):
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
            StructuredLogger.warning(
                f"Prompt adaptation failed: {e}",
                correlation_id=correlation_id,
            )
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
            return self._complete(self.system_prompt, prompt)
        except Exception as e:
            # Return original prompt on error, but warn about failure
            StructuredLogger.warning(f"Prompt enhancement failed: {e}")
            return prompt

    def _complete(self, system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
        """Run one completion against the configured prompt model.

        Shared by enhance() and enhance_variants() so the provider branching
        cannot drift between them.
        """
        prompt_model = self.prompt_model
        if not prompt_model:
            return user_prompt
        api_key = prompt_model.get("api_key", "")
        if not api_key:
            return user_prompt

        if prompt_model["provider"] == "google_gemini":
            client = get_genai_client(api_key, timeout=enhance_timeout)
            gen_config: dict[str, Any] | None = (
                {"response_mime_type": "application/json"} if json_mode else None
            )
            response = client.models.generate_content(
                model=prompt_model["id"],
                contents=f"{system_prompt}\n\n{user_prompt}",
                **({"config": gen_config} if gen_config else {}),
            )
            if not response.candidates or len(response.candidates) == 0:
                raise ValueError("Gemini returned empty candidates")
            return response.candidates[0].content.parts[0].text.strip()

        client_kwargs: dict[str, Any] = {"timeout": enhance_timeout}
        if "base_url" in prompt_model:
            client_kwargs["base_url"] = prompt_model["base_url"]
        client = get_openai_client(api_key, **client_kwargs)

        model_id = prompt_model["id"]
        completion_params: dict[str, Any] = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **_get_model_params(model_id),
        }
        # Only ask for JSON mode where it is known to exist. A custom
        # base_url means an OpenAI-compatible third party, and many of those
        # reject response_format outright. Sending it there would fail the
        # call and drop /enhance back to returning the same prompt twice,
        # which is the bug this method exists to remove.
        if json_mode and "base_url" not in prompt_model:
            completion_params["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**completion_params)
        content = response.choices[0].message.content
        return content.strip() if content else ""

    VARIANTS_SYSTEM_PROMPT = """You expand a user's image prompt into two \
distinct versions.

Return ONLY JSON of the form:
{"short": "...", "long": "..."}

- "short": one tight sentence. Adds the most valuable missing detail (subject,
  lighting or style) and nothing else. Suitable when the user wants the model
  to retain interpretive freedom.
- "long": two to four sentences. Adds composition, lighting, mood, and style
  or artistic reference. Suitable when the user wants tight control.

Both must describe the same subject as the original. "long" must not simply
be "short" with words appended; they are different levels of direction, not
lengths of the same sentence."""

    def enhance_variants(self, prompt: str) -> tuple[str, str]:
        """Return (short, long) enhanced variants of ``prompt``.

        /enhance previously returned the SAME string for both, while the UI
        renders a short/long toggle and a Use button that picks between them.
        The control looked functional and did nothing.

        One LLM call produces both, so this costs exactly what the single
        enhancement cost before and COST_ENHANCE_USD_MICROS stays accurate.
        Two calls would have doubled the price of an endpoint that is still
        unauthenticated.

        Falls back to the previous behaviour (the same string twice) rather
        than failing: a degraded toggle beats a broken button.
        """
        if not prompt:
            return prompt, prompt
        if not self.is_available:
            return prompt, prompt

        try:
            raw = self._complete(self.VARIANTS_SYSTEM_PROMPT, prompt, json_mode=True)
            data = json.loads(raw)
            short = (data.get("short") or "").strip()
            long_ = (data.get("long") or "").strip()
            # Identical variants are rejected too: that is the original bug
            # (a toggle over one string) arriving by a different route.
            if short and long_ and short != long_:
                return short, long_
            StructuredLogger.warning(
                "Enhance variants unusable (missing or identical); returning the original prompt"
            )
        except Exception as e:
            StructuredLogger.warning(f"Enhance variants failed: {e}")

        # Return the original rather than retrying. A second call would make
        # this endpoint cost twice what COST_ENHANCE_USD_MICROS records, so
        # the failure path would silently under-count spend -- and /enhance is
        # still unauthenticated, so that is the path an attacker can force.
        return prompt, prompt

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
