"""
Unit tests for content filtering utilities
"""

import pytest
from src.utils.content_filter import ContentFilter


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
            assert content_filter.is_safe(prompt) is True, f"Safe prompt marked unsafe: {prompt}"

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
            assert content_filter.is_safe(prompt) is False, f"NSFW prompt marked safe: {prompt}"

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
        assert content_filter.is_safe("") is True

    def test_keyword_within_larger_prompt(self):
        """Test that keywords are detected within larger prompts"""
        content_filter = ContentFilter()

        # Keyword in middle of sentence
        assert content_filter.check_prompt("a beautiful sunset with nude figures in the foreground") is True

        # Keyword at start
        assert content_filter.check_prompt("violent scene with explosions") is True

        # Keyword at end
        assert content_filter.check_prompt("artistic portrait that is explicit") is True

    def test_add_blocked_keyword(self):
        """Test adding new blocked keywords"""
        content_filter = ContentFilter()

        # Initially safe
        assert content_filter.check_prompt("unicorn fantasy") is False

        # Add keyword
        content_filter.add_blocked_keyword("unicorn")

        # Now should be blocked
        assert content_filter.check_prompt("unicorn fantasy") is True

        # Case insensitive
        assert content_filter.check_prompt("UNICORN adventure") is True

    def test_remove_blocked_keyword(self):
        """Test removing blocked keywords"""
        content_filter = ContentFilter()

        # Initially blocked
        assert content_filter.check_prompt("nude portrait") is True

        # Remove keyword
        content_filter.remove_blocked_keyword("nude")

        # Now should be safe
        assert content_filter.check_prompt("nude portrait") is False

    def test_get_blocked_keywords(self):
        """Test retrieving list of blocked keywords"""
        content_filter = ContentFilter()

        keywords = content_filter.get_blocked_keywords()

        # Should return a list
        assert isinstance(keywords, list)

        # Should contain expected keywords
        assert 'nude' in keywords
        assert 'nsfw' in keywords
        assert 'gore' in keywords

        # Should be a copy (not reference)
        keywords.append('test')
        assert 'test' not in content_filter.get_blocked_keywords()

    def test_add_duplicate_keyword(self):
        """Test that adding duplicate keywords doesn't create duplicates"""
        content_filter = ContentFilter()

        initial_count = len(content_filter.get_blocked_keywords())

        # Add keyword that already exists
        content_filter.add_blocked_keyword("nude")

        final_count = len(content_filter.get_blocked_keywords())

        assert initial_count == final_count

    def test_remove_nonexistent_keyword(self):
        """Test removing a keyword that doesn't exist"""
        content_filter = ContentFilter()

        initial_keywords = content_filter.get_blocked_keywords()

        # Remove keyword that doesn't exist
        content_filter.remove_blocked_keyword("nonexistent_keyword_12345")

        final_keywords = content_filter.get_blocked_keywords()

        # Should remain unchanged
        assert initial_keywords == final_keywords

    def test_partial_word_match(self):
        """Test that keywords match as substrings"""
        content_filter = ContentFilter()

        # 'nude' should match 'denuded', 'seminude', etc.
        assert content_filter.check_prompt("a denuded landscape") is True

        # This is expected behavior for simple keyword filtering
        # More sophisticated filtering would use word boundaries

    def test_safe_words_containing_blocked_substrings(self):
        """Test edge cases where safe words contain blocked substrings"""
        content_filter = ContentFilter()

        # These might be false positives with simple keyword matching
        # Testing actual behavior
        result = content_filter.check_prompt("a hateful of apples")  # Contains 'hate'
        # This will be blocked because 'hate' is in 'hateful'
        assert result is True

        # For production use, would need word boundary detection
        # Currently testing the actual implementation

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
