"""
Unit tests for content filtering utilities
"""

import pytest

from utils.content_filter import ContentFilter


class TestContentFilter:
    """Tests for ContentFilter class"""

    def test_safe_prompt_passes(self):
        """Test that safe prompts are not blocked"""
        content_filter = ContentFilter()

        safe_prompts = [
            "a beautiful sunset over the ocean",
            "a cute cat playing with yarn",
            "a mountain landscape with snow-capped peaks",
            "a futuristic city with flying cars",
            "a portrait of a smiling person",
            "abstract geometric shapes in vibrant colors"
        ]

        for prompt in safe_prompts:
            assert content_filter.check_prompt(prompt) is False, f"Safe prompt was blocked: {prompt}"

    def test_nsfw_keywords_blocked(self):
        """Test that NSFW keywords are blocked"""
        content_filter = ContentFilter()

        nsfw_prompts = [
            "a nude portrait",
            "naked person on beach",
            "NSFW content warning",
            "explicit adult material",
            "pornographic imagery",
            "sexual content",
            "XXX rated scene",
            "erotic art",
            "adult content only",
            "lewd anime character"
        ]

        for prompt in nsfw_prompts:
            assert content_filter.check_prompt(prompt) is True, f"NSFW prompt was not blocked: {prompt}"

    def test_violence_keywords_blocked(self):
        """Test that violent content keywords are blocked"""
        content_filter = ContentFilter()

        violent_prompts = [
            "gore and blood scene",
            "violent battle",
            "gruesome injury",
            "mutilated body"
        ]

        for prompt in violent_prompts:
            assert content_filter.check_prompt(prompt) is True, f"Violent prompt was not blocked: {prompt}"

    def test_hate_keywords_blocked(self):
        """Test that hate speech keywords are blocked"""
        content_filter = ContentFilter()

        hate_prompts = [
            "hate speech example",
            "racist imagery",
            "offensive content",
            "discriminatory message"
        ]

        for prompt in hate_prompts:
            assert content_filter.check_prompt(prompt) is True, f"Hate prompt was not blocked: {prompt}"

    def test_case_insensitive_filtering(self):
        """Test that filtering is case-insensitive"""
        content_filter = ContentFilter()

        variants = [
            "NUDE portrait",
            "Nude Portrait",
            "nude PORTRAIT",
            "nUdE pOrTrAiT"
        ]

        for prompt in variants:
            assert content_filter.check_prompt(prompt) is True, f"Case variant was not blocked: {prompt}"

    def test_empty_prompt_is_safe(self):
        """Test that empty prompts are considered safe"""
        content_filter = ContentFilter()

        assert content_filter.check_prompt("") is False
        assert content_filter.check_prompt(None) is False

    def test_keyword_within_larger_prompt(self):
        """Test that keywords are detected within larger prompts"""
        content_filter = ContentFilter()

        # Keyword in middle of sentence
        assert content_filter.check_prompt("a beautiful sunset with nude figures in the foreground") is True

        # Keyword at start
        assert content_filter.check_prompt("violent scene with explosions") is True

        # Keyword at end
        assert content_filter.check_prompt("artistic portrait that is explicit") is True

    def test_word_boundary_avoids_false_positives(self):
        """Test that word-boundary matching avoids false positives."""
        content_filter = ContentFilter()

        # 'nude' should NOT match 'denuded' (not a standalone word)
        assert content_filter.check_prompt("a denuded landscape") is False

        # 'gore' should NOT match 'gorgeous'
        assert content_filter.check_prompt("a gorgeous sunset") is False

        # 'hate' should NOT match 'fate' (different word)
        assert content_filter.check_prompt("whatever the fate") is False

    def test_standalone_blocked_words_still_caught(self):
        """Test that standalone blocked words are still caught."""
        content_filter = ContentFilter()

        assert content_filter.check_prompt("pure hate speech") is True
        assert content_filter.check_prompt("show me nude art") is True
        assert content_filter.check_prompt("add blood effects") is True

    def test_multiple_blocked_keywords_in_prompt(self):
        """Test prompts containing multiple blocked keywords"""
        content_filter = ContentFilter()

        prompt = "violent and explicit nude content"

        # Should be blocked (contains multiple keywords)
        assert content_filter.check_prompt(prompt) is True

    def test_whitespace_and_punctuation(self):
        """Test that keywords work with various whitespace and punctuation"""
        content_filter = ContentFilter()

        prompts = [
            "nude!",
            "nude?",
            "nude.",
            "nude,",
            "  nude  ",
            "\tnude\n",
            "(nude)",
            "[nude]"
        ]

        for prompt in prompts:
            assert content_filter.check_prompt(prompt) is True, f"Keyword with punctuation not blocked: {repr(prompt)}"


class TestContentFilterEvasion:
    """Tests for filter evasion resistance."""

    def test_leetspeak_evasion(self):
        content_filter = ContentFilter()
        assert content_filter.check_prompt("nud3") is True
        assert content_filter.check_prompt("3xplicit") is True
        assert content_filter.check_prompt("h@t3") is True
        assert content_filter.check_prompt("n4k3d") is True
        assert content_filter.check_prompt("vi0l3nt") is True

    def test_spaced_evasion(self):
        content_filter = ContentFilter()
        assert content_filter.check_prompt("n u d e") is True
        assert content_filter.check_prompt("n-u-d-e") is True
        assert content_filter.check_prompt("n_u_d_e") is True
        assert content_filter.check_prompt("n.u.d.e") is True
        assert content_filter.check_prompt("e x p l i c i t") is True

    def test_unicode_evasion(self):
        content_filter = ContentFilter()
        # Accented characters
        assert content_filter.check_prompt("nud\u00e9") is True  # nudé
        assert content_filter.check_prompt("gor\u00e9") is True  # goré

    def test_combined_evasion(self):
        content_filter = ContentFilter()
        # Leetspeak + spacing
        assert content_filter.check_prompt("n.u.d.3") is True
        assert content_filter.check_prompt("3 x p l 1 c 1 t") is True

    def test_clean_prompts_still_pass(self):
        content_filter = ContentFilter()
        safe = [
            "a beautiful landscape with mountains",
            "a cat sitting on a window sill",
            "abstract art with bright colors",
            "a futuristic robot in a garden",
            "a painting of a sunset at the beach",
        ]
        for prompt in safe:
            assert content_filter.check_prompt(prompt) is False, f"Clean prompt blocked: {prompt}"


# ---------------------------------------------------------------------------
# Task 5: false positives on a creative image product, and the broken leet map
# ---------------------------------------------------------------------------


class TestBenignCollocations:
    """"blood moon" is an astronomical event, not gore.

    Six terms -- blood, gore, hate, violent, sexual, offensive -- were
    word-boundary blocked, so a creative image product rejected "blood
    orange still life" with INAPPROPRIATE_CONTENT. They are now checked
    against a short, literal allowlist of benign collocations first.
    """

    @pytest.mark.parametrize(
        "prompt",
        [
            "a blood moon over the desert",
            "blood orange still life",
            "a blood-red sunset",
            "a diagram of a blood cell",
            "a blood vessel under a microscope",
            "a duel fought in cold blood",
            "a gore-tex jacket in the rain",
            "an offensive line in a football stadium",
            "a violent storm over the plains",
            "sexual dimorphism in tropical birds",
        ],
    )
    def test_benign_collocations_are_not_blocked(self, prompt):
        assert ContentFilter().check_prompt(prompt) is False, prompt

    def test_the_term_outside_its_collocation_still_blocks(self):
        """The allowlist exempts the phrase, not the word.

        Without this the allowlist would be an evasion vector: append "blood
        moon" to anything and the whole prompt is exempt.
        """
        cf = ContentFilter()
        assert cf.check_prompt("a blood moon and blood everywhere") is True
        assert cf.check_prompt("a gore-tex jacket covered in gore") is True

    def test_unambiguous_terms_have_no_allowlist(self):
        """Loosening the ambiguous six must not loosen the other thirteen."""
        cf = ContentFilter()
        for prompt in (
            "nude portrait",
            "naked person on beach",
            "nsfw content",
            "explicit adult material",
            "pornographic imagery",
            "xxx rated scene",
            "erotic art",
            "lewd anime character",
            "adult content only",
            "mutilated body",
            "gruesome injury",
            "racist imagery",
            "discriminatory message",
        ):
            assert cf.check_prompt(prompt) is True, prompt


class TestLeetMapRegression:
    """_LEET_MAP mapped 5->t and 7->y instead of 5->s and 7->t.

    The normalisation existed to defeat leetspeak evasion and was corrupting
    the very strings it was meant to catch.
    """

    def test_n5fw_normalises_to_nsfw_which_the_old_five_to_t_map_turned_into_ntfw(self):
        assert ContentFilter().check_prompt("n5fw content") is True

    def test_ero7ic_normalises_to_erotic_which_the_old_seven_to_y_map_turned_into_eroyic(self):
        assert ContentFilter().check_prompt("ero7ic art") is True

    def test_explici7_normalises_to_explicit(self):
        assert ContentFilter().check_prompt("explici7 material") is True

    def test_the_map_substitutes_the_conventional_letters(self):
        from utils.content_filter import _normalize_base

        assert _normalize_base("013457@$8") == "oieastasb"

    def test_n5de_does_not_normalise_to_nude_and_is_not_blocked(self):
        """Asserting the answer the corrected map actually gives, not a guess.

        5 maps to s, so "n5de" becomes "nsde" -- not a keyword. The old map
        made it "ntde", which was equally not a keyword; this string was never
        caught and still is not. Recorded so the next reader does not assume
        it was.
        """
        from utils.content_filter import _normalize_base

        assert _normalize_base("n5de") == "nsde"
        assert ContentFilter().check_prompt("n5de") is False


def test_a_hateful_expression_was_already_safe():
    """Documented as a false positive in the audit; it was not one.

    ``\\bhate\\b`` does not match inside "hateful" -- there is no word
    boundary between the "e" and the "f". Asserted so the claim is settled
    rather than repeated.
    """
    assert ContentFilter().check_prompt("a hateful expression") is False


# ---------------------------------------------------------------------------
# Plural collocations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        "blood orange",
        "blood oranges",
        "a still life with blood oranges",
        "blood vessel",
        "blood vessels",
        "blood cells",
        "violent wave",
        "violent waves",
        "offensive lines",
        "blood moons",
    ],
)
def test_benign_collocations_pass_in_singular_and_plural(prompt):
    """The allowlist matched the singular only, so the plural was rejected.

    "blood orange" passed and "blood oranges" did not -- the trailing \\b has no
    boundary before the s, the entry never fired, a bare "blood" survived into
    the residue, and the filter rejected the exact phrase the entry exists to
    permit. Plural is the more natural phrasing for most of these, so the
    common case was the broken one.
    """
    assert ContentFilter().check_prompt(prompt) is False, prompt


@pytest.mark.parametrize(
    "prompt",
    [
        "blood everywhere",
        "covered in blood",
        "gore",
        "extremely violent",
        "a blood moon and blood everywhere",
    ],
)
def test_plural_tolerance_does_not_open_the_filter(prompt):
    """Widening the allowlist must not widen what gets through it.

    The last case is the one that matters: an allowlisted collocation next to a
    bare use of the same keyword is still blocked, because the allowlist
    removes text rather than short-circuiting.
    """
    assert ContentFilter().check_prompt(prompt) is True, prompt
