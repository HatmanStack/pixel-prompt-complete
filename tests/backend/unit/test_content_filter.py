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

        # 'hate' should NOT match 'hateful' (the word is 'hateful', not 'hate')
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
