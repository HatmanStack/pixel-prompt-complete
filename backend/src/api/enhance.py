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
            return None


        # Get prompt enhancement model
        prompt_model = self.model_registry.get_prompt_model()

        if not prompt_model:
            return prompt

        try:

            provider = prompt_model['provider']

            # Branch based on provider type
            if provider == 'google_gemini':
                # Use Google genai client for Gemini
                api_key = prompt_model.get('api_key', '')
                if not api_key:
                    return prompt

                client = genai.Client(api_key=api_key)

                response = client.models.generate_content(
                    model=prompt_model['id'],
                    contents=f"{self.system_prompt}\n\n{prompt}"
                )

                # Extract text from Gemini response
                if not response.candidates or len(response.candidates) == 0:
                    raise ValueError("Gemini returned empty candidates")

                enhanced = response.candidates[0].content.parts[0].text.strip()

            else:
                # Use OpenAI client for OpenAI and OpenAI-compatible providers
                api_key = prompt_model.get('api_key', '')
                if not api_key:
                    return prompt

                client_kwargs = {
                    'api_key': api_key,
                    'timeout': 30.0
                }

                # Support custom base_url for OpenAI-compatible providers
                if 'base_url' in prompt_model:
                    client_kwargs['base_url'] = prompt_model['base_url']

                client = OpenAI(**client_kwargs)

                # Determine model identifier
                # Use configured model ID from prompt_model
                model_id = prompt_model['id']


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
                enhanced = response.choices[0].message.content
                if enhanced:
                    enhanced = enhanced.strip()
                else:
                    enhanced = ""


            return enhanced

        except Exception as e:
            import traceback
            traceback.print_exc()
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
