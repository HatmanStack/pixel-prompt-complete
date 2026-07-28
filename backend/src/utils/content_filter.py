"""Cheap keyword pre-filter for prompts.

What this is: a keyword match in front of providers that run their own
moderation. It exists so an obviously disallowed prompt is refused before it
costs four provider calls, and so the rewritten prompt an LLM produces is
checked as well as the one the user typed.

What this is **not**: the moderation itself. Google, OpenAI, Adobe and Bedrock
each enforce their own policies on every request, and they are far better at
it than a word list. Being clear about that is what justifies loosening it:
a false positive here is a refused sale on a creative product, while a false
negative is caught downstream by four independent filters.

That framing is why the keyword list has two tiers. Terms whose only ordinary
use is the disallowed one stay word-boundary blocked. Terms with common benign
uses -- "blood moon", "gore-tex", "sexual dimorphism" -- consult a short,
literal allowlist first. No sentiment analysis: pretending a keyword filter is
more than a keyword filter is how it came to reject blood oranges.
"""

import re
import unicodedata

# Leetspeak substitution map: 0->o, 1->i, 3->e, 4->a, 5->s, 7->t, @->a,
# $->s, 8->b.
#
# This previously mapped 5->t and 7->y, which are not the conventional
# substitutions -- so the normalisation that exists to defeat leetspeak was
# corrupting the strings it was meant to catch: "n5fw" normalised to "ntfw"
# and "ero7ic" to "eroyic", neither of which is a keyword. str.maketrans
# raises when the two strings differ in length, so a typo here fails at
# import, which is the good case.
_LEET_MAP = str.maketrans("013457@$8", "oieastasb")

# Pattern to detect deliberate character-separated evasion (e.g. "n.u.d.e", "n u d e")
_EVASION_PATTERN = re.compile(r"(?:\w[\s\-_\.]+){2,}\w")


def _normalize_base(text: str) -> str:
    """
    Base normalization: lowercase, unicode, leetspeak.

    1. Lowercase
    2. Unicode NFKD normalize + strip combining marks (accents, homoglyphs)
    3. Leetspeak substitution (0→o, 1→i, 3→e, etc.)
    """
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.translate(_LEET_MAP)
    return text


def _normalize_words(text: str) -> str:
    """Normalize preserving word boundaries (for word-boundary matching)."""
    text = _normalize_base(text)
    text = re.sub(r"[\s\-_\.]+", " ", text).strip()
    return text


# Terms whose ordinary uses are all disallowed here. No allowlist: these are
# not ambiguous, and giving them one would be an evasion vector.
UNAMBIGUOUS_KEYWORDS = (
    "nude",
    "naked",
    "nsfw",
    "explicit",
    "pornographic",
    "xxx",
    "erotic",
    "lewd",
    "adult content",
    "mutilated",
    "gruesome",
    "racist",
    "discriminatory",
)

# Terms with common benign uses on an image product. Blocked only where they
# are not part of a listed collocation.
CONTEXT_DEPENDENT_KEYWORDS = (
    "blood",
    "gore",
    "hate",
    "violent",
    "sexual",
    "offensive",
)

# Deliberately short and literal. Every entry is a phrase someone plausibly
# asks an image model for, and the list is meant to be read in full by whoever
# next has to decide whether to add to it. Hyphens need no separate entries:
# _normalize_words collapses them, so "blood-red" and "gore-tex" are already
# covered by "blood red" and "gore tex".
#
# Single words containing a term need no entry either -- "bloodhound",
# "lifeblood" and "asexual" have no word boundary around the term, so \b
# never matches inside them.
#
# Write entries in the SINGULAR. _collocation_pattern appends an optional
# plural, so "blood orange" covers "blood oranges" -- but the reverse does not
# hold, and a plural entry leaves its own singular blocked.
BENIGN_COLLOCATIONS = (
    "blood moon",
    "blood orange",
    "blood red",
    "blood cell",
    "blood vessel",
    "blood pressure",
    "blood type",
    "cold blood",
    "bad blood",
    "gore tex",
    "al gore",
    "hate mail",
    "violent storm",
    "violent wave",
    "violent wind",
    "sexual dimorphism",
    "sexual reproduction",
    "offensive line",
    "charm offensive",
)


def _word_pattern(phrase: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(_normalize_words(phrase)) + r"\b")


def _collocation_pattern(phrase: str) -> re.Pattern[str]:
    """Allowlist pattern, tolerant of a plural on the final word.

    ``_word_pattern``'s trailing ``\\b`` means "blood orange" does not match
    "blood oranges": the ``s`` continues the word, so there is no boundary
    there. The allowlist then never fires, "blood" survives into the residue,
    and the filter rejects the exact phrase the entry exists to permit --
    reproducing the false positive this list was written to fix.

    Plural is the more natural phrasing for most of these ("blood oranges",
    "blood vessels", "violent waves"), so matching only the singular misses
    the common case rather than an edge case.

    Deliberately a separate builder from ``_word_pattern`` rather than a change
    to it: that one also compiles the two *blocking* keyword lists, and
    widening those would change what the filter rejects, which is not what
    this fixes.
    """
    return re.compile(r"\b" + re.escape(_normalize_words(phrase)) + r"(?:e?s)?\b")


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

    def __init__(self) -> None:
        """Initialize Content Filter with blocked keywords."""
        self._unambiguous_patterns = [_word_pattern(kw) for kw in UNAMBIGUOUS_KEYWORDS]
        self._context_patterns = [_word_pattern(kw) for kw in CONTEXT_DEPENDENT_KEYWORDS]
        self._benign_patterns = [_collocation_pattern(p) for p in BENIGN_COLLOCATIONS]
        # Pre-normalize keywords for evasion check. Both tiers participate:
        # spelling a word out letter by letter is deliberate, so the benign
        # reading no longer applies to it.
        self._collapsed_keywords = set(
            re.sub(r"\s+", "", _normalize_words(kw))
            for kw in (*UNAMBIGUOUS_KEYWORDS, *CONTEXT_DEPENDENT_KEYWORDS)
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

        # Pass 1a: unambiguous terms, word-boundary matched.
        normalized_words = _normalize_words(prompt)
        for pattern in self._unambiguous_patterns:
            if pattern.search(normalized_words):
                return True

        # Pass 1b: context-dependent terms, with the benign collocations
        # removed first. Removing rather than short-circuiting on a match is
        # what keeps the allowlist from becoming an evasion vector: "a blood
        # moon and blood everywhere" still leaves a bare "blood" behind, and
        # is still blocked.
        residue = normalized_words
        for pattern in self._benign_patterns:
            residue = pattern.sub(" ", residue)
        for pattern in self._context_patterns:
            if pattern.search(residue):
                return True

        # Pass 2: evasion detection — find char-separated sequences, collapse them
        base = _normalize_base(prompt)
        for match in _EVASION_PATTERN.finditer(base):
            collapsed = re.sub(r"[\s\-_\.]+", "", match.group())
            for keyword in self._collapsed_keywords:
                if keyword in collapsed:
                    return True

        return False
