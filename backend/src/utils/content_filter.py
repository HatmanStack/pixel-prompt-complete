"""
Content Moderation module for Pixel Prompt Complete.

Implements keyword-based NSFW and inappropriate content filtering
with normalization to resist common evasion techniques.
"""

import re
import unicodedata

# Leetspeak substitution map
_LEET_MAP = str.maketrans('013457@$8', 'oieatyasb')

# Pattern to detect deliberate character-separated evasion (e.g. "n.u.d.e", "n u d e")
_EVASION_PATTERN = re.compile(r'(?:\w[\s\-_\.]+){2,}\w')


def _normalize_base(text: str) -> str:
    """
    Base normalization: lowercase, unicode, leetspeak.

    1. Lowercase
    2. Unicode NFKD normalize + strip combining marks (accents, homoglyphs)
    3. Leetspeak substitution (0→o, 1→i, 3→e, etc.)
    """
    text = text.lower()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.translate(_LEET_MAP)
    return text


def _normalize_words(text: str) -> str:
    """Normalize preserving word boundaries (for word-boundary matching)."""
    text = _normalize_base(text)
    text = re.sub(r'[\s\-_\.]+', ' ', text).strip()
    return text


class ContentFilter:
    """
    Content moderation filter for prompts.

    Uses keyword-based filtering with normalization to detect
    NSFW/inappropriate content even with evasion attempts.
    Two-pass approach:
    1. Word-boundary matching on space-preserved text (avoids false positives)
    2. Evasion detection: collapse char-separated sequences (e.g. "n.u.d.e")
       and check for keywords
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
        # Pre-compile word-boundary patterns (space-preserved normalization)
        self._word_patterns = [
            re.compile(r'\b' + re.escape(_normalize_words(kw)) + r'\b')
            for kw in raw_keywords
        ]
        # Pre-normalize keywords for evasion check
        self._collapsed_keywords = set(
            re.sub(r'\s+', '', _normalize_words(kw)) for kw in raw_keywords
        )

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

        # Pass 1: word-boundary matching (catches normal usage, avoids false positives)
        normalized_words = _normalize_words(prompt)
        for pattern in self._word_patterns:
            if pattern.search(normalized_words):
                return True

        # Pass 2: evasion detection — find char-separated sequences, collapse them
        base = _normalize_base(prompt)
        for match in _EVASION_PATTERN.finditer(base):
            collapsed = re.sub(r'[\s\-_\.]+', '', match.group())
            for keyword in self._collapsed_keywords:
                if keyword in collapsed:
                    return True

        return False
