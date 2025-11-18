"""
Prompt Enhancement module for Pixel Prompt Complete.

Uses configured LLM to expand short prompts into detailed image generation prompts.
"""

from typing import Optional
from openai import OpenAI
from google import genai


class PromptEnhancer:
    """
    Enhances short prompts into detailed image generation prompts using LLM.
    """

    def __init__(self, model_registry):
        """
        Initialize Prompt Enhancer.

        Args:
            model_registry: ModelRegistry instance
        """
        self.model_registry = model_registry

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

    def enhance(self, prompt: str) -> Optional[str]:
        """
        Enhance a short prompt into a detailed one.

        Args:
            prompt: Short prompt to enhance

        Returns:
            Enhanced prompt string or None if enhancement fails
        """
        if not prompt:
            print("[ENHANCE] Empty prompt provided")
            return None

        print(f"[ENHANCE] Starting enhancement for prompt: '{prompt[:50]}...'")

        # Get prompt enhancement model
        prompt_model = self.model_registry.get_prompt_model()

        if not prompt_model:
            print("[ENHANCE] ERROR: No prompt model configured!")
            print(f"[ENHANCE] PROMPT_MODEL_INDEX: {self.model_registry.prompt_model_index}")
            print(f"[ENHANCE] Available models: {len(self.model_registry.get_all_models())}")
            print("[ENHANCE] Returning original prompt (no enhancement)")
            return prompt

        try:
            print(f"[ENHANCE] Found prompt model: {prompt_model['id']}")
            print(f"[ENHANCE] Provider: {prompt_model['provider']}")
            print(f"[ENHANCE] Has API key: {bool(prompt_model.get('api_key'))}")
            print(f"[ENHANCE] Has base URL: {bool(prompt_model.get('base_url'))}")

            provider = prompt_model['provider']

            # Branch based on provider type
            if provider == 'google_gemini':
                print("[ENHANCE] Using Google Gemini for enhancement")
                # Use Google genai client for Gemini
                api_key = prompt_model.get('api_key', '')
                if not api_key:
                    print("[ENHANCE] ERROR: No API key configured for Google Gemini")
                    print("[ENHANCE] Returning original prompt")
                    return prompt

                print(f"[ENHANCE] Initializing Google Gemini client with model: {prompt_model['id']}")
                client = genai.Client(api_key=api_key)

                print("[ENHANCE] Calling Gemini API...")
                response = client.models.generate_content(
                    model=prompt_model['id'],
                    contents=f"{self.system_prompt}\n\n{prompt}"
                )

                # Extract text from Gemini response
                if not response.candidates or len(response.candidates) == 0:
                    print("[ENHANCE] ERROR: Gemini returned empty candidates")
                    raise ValueError("Gemini returned empty candidates")

                enhanced = response.candidates[0].content.parts[0].text.strip()
                print(f"[ENHANCE] Gemini response received: {len(enhanced)} characters")

            else:
                # Use OpenAI client for OpenAI and OpenAI-compatible providers
                print(f"[ENHANCE] Using OpenAI-compatible client for provider: {provider}")
                api_key = prompt_model.get('api_key', '')
                if not api_key:
                    print(f"[ENHANCE] ERROR: No API key configured for provider: {provider}")
                    print("[ENHANCE] Returning original prompt")
                    return prompt

                client_kwargs = {
                    'api_key': api_key,
                    'timeout': 30.0
                }

                # Support custom base_url for OpenAI-compatible providers
                if 'base_url' in prompt_model:
                    client_kwargs['base_url'] = prompt_model['base_url']
                    print(f"[ENHANCE] Using custom base URL: {prompt_model['base_url']}")

                print(f"[ENHANCE] Initializing OpenAI client (timeout: 30s)")
                client = OpenAI(**client_kwargs)

                # Determine model identifier
                # Use configured model ID from prompt_model
                model_id = prompt_model['id']
                print(f"[ENHANCE] Using configured model ID: {model_id}")

                print("[ENHANCE] Calling OpenAI-compatible API...")

                # GPT-5 and newer models have different API requirements
                completion_params = {
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt}
                    ]
                }

                # GPT-5 specific parameters
                if "gpt-5" in model_id:
                    # GPT-5 uses reasoning tokens, need more tokens for reasoning + output
                    completion_params["max_completion_tokens"] = 1000
                    # GPT-5 only supports temperature=1 (default), so omit it
                # GPT-4o and newer use max_completion_tokens
                elif "gpt-4o" in model_id:
                    completion_params["max_completion_tokens"] = 200
                    completion_params["temperature"] = 0.7
                # Older models use max_tokens
                else:
                    completion_params["max_tokens"] = 200
                    completion_params["temperature"] = 0.7

                response = client.chat.completions.create(**completion_params)

                # Extract enhanced prompt
                print(f"[ENHANCE] Full response: {response}")
                enhanced = response.choices[0].message.content
                if enhanced:
                    enhanced = enhanced.strip()
                else:
                    enhanced = ""
                    print(f"[ENHANCE] WARNING: GPT response content is None/empty")
                print(f"[ENHANCE] OpenAI response received: {len(enhanced)} characters")

            print(f"[ENHANCE] SUCCESS!")
            print(f"[ENHANCE] Original: {prompt}")
            print(f"[ENHANCE] Enhanced: {enhanced[:100]}...")

            return enhanced

        except Exception as e:
            print(f"[ENHANCE] EXCEPTION occurred: {type(e).__name__}")
            print(f"[ENHANCE] Error message: {str(e)}")
            import traceback
            print(f"[ENHANCE] Traceback:")
            traceback.print_exc()
            print("[ENHANCE] Returning original prompt due to error")
            # Return original prompt on error
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
