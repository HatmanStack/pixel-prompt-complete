"""
Content Moderation module for Pixel Prompt Complete.

Implements keyword-based NSFW and inappropriate content filtering.
"""


class ContentFilter:
    """
    Content moderation filter for prompts.

    Uses keyword-based filtering to detect NSFW/inappropriate content.
    """

    def __init__(self):
        """Initialize Content Filter with blocked keywords."""
        # List of blocked keywords/phrases (case-insensitive)
        self.blocked_keywords = [
            # NSFW terms
            'nude', 'naked', 'nsfw', 'explicit', 'pornographic', 'sexual',
            'xxx', 'erotic', 'adult content', 'lewd',
            # Violence
            'gore', 'blood', 'violent', 'gruesome', 'mutilated',
            # Harmful content
            'hate', 'racist', 'offensive', 'discriminatory',
            # Add more as needed based on requirements
        ]


    def check_prompt(self, prompt: str) -> bool:
        """
        Check if prompt contains inappropriate content.

        Args:
            prompt: Text prompt to check

        Returns:
            True if prompt is NSFW/inappropriate (should be blocked), False if safe
        """
        if not prompt:
            return False

        # Convert to lowercase for case-insensitive matching
        prompt_lower = prompt.lower()

        # Check each blocked keyword
        for keyword in self.blocked_keywords:
            if keyword in prompt_lower:
                return True

        # Prompt is safe
        return False
