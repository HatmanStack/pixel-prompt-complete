"""
Content Moderation module for Pixel Prompt Complete.

Implements keyword-based NSFW and inappropriate content filtering
with normalization to resist common evasion techniques.
"""

import re
import unicodedata

# Leetspeak substitution map
_LEET_MAP = str.maketrans('013457@$8', 'oieatyasb')


def _normalize(text: str) -> str:
    """
    Normalize text to defeat common filter evasion.

    1. Lowercase
    2. Unicode NFKD normalize + strip combining marks (accents, homoglyphs)
    3. Leetspeak substitution (0→o, 1→i, 3→e, etc.)
    4. Collapse whitespace, hyphens, underscores, dots
    """
    text = text.lower()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.translate(_LEET_MAP)
    text = re.sub(r'[\s\-_\.]+', '', text)
    return text


class ContentFilter:
    """
    Content moderation filter for prompts.

    Uses keyword-based filtering with normalization to detect
    NSFW/inappropriate content even with evasion attempts.
    """

    def __init__(self):
        """Initialize Content Filter with blocked keywords."""
        raw_keywords = [
            # NSFW terms
            'nude', 'naked', 'nsfw', 'explicit', 'pornographic', 'sexual',
            'xxx', 'erotic', 'adult content', 'lewd',
            # Violence
            'gore', 'blood', 'violent', 'gruesome', 'mutilated',
            # Harmful content
            'hate', 'racist', 'offensive', 'discriminatory',
        ]
        # Pre-normalize keywords once at init
        self.blocked_keywords = [_normalize(kw) for kw in raw_keywords]

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

        normalized = _normalize(prompt)

        for keyword in self.blocked_keywords:
            if keyword in normalized:
                return True

        return False
