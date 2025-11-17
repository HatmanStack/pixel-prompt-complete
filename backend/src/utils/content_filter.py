"""
Content Moderation module for Pixel Prompt Complete.

Implements keyword-based NSFW and inappropriate content filtering.
"""

from typing import List


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

        print(f"Content filter initialized with {len(self.blocked_keywords)} blocked keywords")

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
                print(f"Content filter triggered: found '{keyword}' in prompt")
                return True

        # Prompt is safe
        return False

    def is_safe(self, prompt: str) -> bool:
        """
        Check if prompt is safe (opposite of check_prompt).

        Args:
            prompt: Text prompt to check

        Returns:
            True if safe, False if inappropriate
        """
        return not self.check_prompt(prompt)

    def add_blocked_keyword(self, keyword: str) -> None:
        """
        Add a keyword to the blocked list.

        Args:
            keyword: Keyword to block (will be converted to lowercase)
        """
        keyword_lower = keyword.lower()
        if keyword_lower not in self.blocked_keywords:
            self.blocked_keywords.append(keyword_lower)
            print(f"Added blocked keyword: {keyword_lower}")

    def remove_blocked_keyword(self, keyword: str) -> None:
        """
        Remove a keyword from the blocked list.

        Args:
            keyword: Keyword to unblock
        """
        keyword_lower = keyword.lower()
        if keyword_lower in self.blocked_keywords:
            self.blocked_keywords.remove(keyword_lower)
            print(f"Removed blocked keyword: {keyword_lower}")

    def get_blocked_keywords(self) -> List[str]:
        """
        Get list of all blocked keywords.

        Returns:
            List of blocked keywords
        """
        return self.blocked_keywords.copy()
