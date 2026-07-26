"""Tests that /enhance returns two genuinely different prompts.

It previously returned the identical string for short_prompt and
long_prompt while the UI rendered a short/long toggle and a Use button that
picked between them. The control looked functional and did nothing.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFRONT_DOMAIN", "test.cloudfront.net")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

SHORT = "A cat on a windowsill in warm afternoon light."
LONG = (
    "A tabby cat curled on a sunlit windowsill, warm afternoon light raking "
    "across weathered wood. Shallow depth of field, dust motes suspended in "
    "the air. Painterly, reminiscent of Andrew Wyeth."
)


def _enhancer(available=True):
    from api.enhance import PromptEnhancer

    e = PromptEnhancer()
    e.prompt_model = {"provider": "openai", "id": "gpt-4o", "api_key": "k"} if available else None
    return e


def test_returns_two_distinct_variants():
    e = _enhancer()
    with patch.object(e, "_complete", return_value=json.dumps({"short": SHORT, "long": LONG})):
        short, long_ = e.enhance_variants("a cat")

    assert short == SHORT
    assert long_ == LONG
    assert short != long_, "the toggle has nothing to toggle between"


def test_uses_a_single_llm_call():
    """Two calls would double the price of an endpoint that is still
    unauthenticated, and would make COST_ENHANCE_USD_MICROS wrong."""
    e = _enhancer()
    with patch.object(
        e, "_complete", return_value=json.dumps({"short": SHORT, "long": LONG})
    ) as mock_complete:
        e.enhance_variants("a cat")
    mock_complete.assert_called_once()
    assert mock_complete.call_args.kwargs["json_mode"] is True


def test_falls_back_when_the_model_returns_junk():
    """A degraded toggle beats a broken button."""
    e = _enhancer()
    with (
        patch.object(e, "_complete", return_value="not json at all"),
        patch.object(e, "enhance_safe", return_value="fallback text"),
    ):
        short, long_ = e.enhance_variants("a cat")
    assert short == long_ == "fallback text"


def test_falls_back_when_a_field_is_missing():
    e = _enhancer()
    with (
        patch.object(e, "_complete", return_value=json.dumps({"short": SHORT})),
        patch.object(e, "enhance_safe", return_value="fallback text"),
    ):
        short, long_ = e.enhance_variants("a cat")
    assert short == long_ == "fallback text"


def test_unconfigured_enhancer_returns_the_original():
    """Open-source mode ships without PROMPT_MODEL_API_KEY."""
    e = _enhancer(available=False)
    assert e.enhance_variants("a cat") == ("a cat", "a cat")


def test_empty_prompt_is_passed_through():
    assert _enhancer().enhance_variants("") == ("", "")


def test_endpoint_returns_both_fields():
    import lambda_function

    with (
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function._daily_spend_exceeded", return_value=False),
        patch("lambda_function._cost_meter"),
        patch("lambda_function.prompt_enhancer") as mock_enh,
    ):
        mock_cf.check_prompt.return_value = False
        mock_enh.enhance_variants.return_value = (SHORT, LONG)
        resp = lambda_function.handle_enhance(
            {
                "body": json.dumps({"prompt": "a cat"}),
                "requestContext": {"http": {"sourceIp": "1.2.3.4", "method": "POST"}},
                "headers": {},
            },
            "corr-1",
        )

    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["short_prompt"] == SHORT
    assert body["long_prompt"] == LONG
    assert body["short_prompt"] != body["long_prompt"]
    assert body["original"] == "a cat"


def test_json_mode_is_requested_from_openai():
    """Without response_format the model will wrap JSON in prose."""
    e = _enhancer()
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({"short": "s", "long": "l"})))]
    )
    with patch("api.enhance.get_openai_client", return_value=client):
        e._complete("sys", "user", json_mode=True)

    params = client.chat.completions.create.call_args.kwargs
    assert params["response_format"] == {"type": "json_object"}


def test_json_mode_is_not_requested_for_plain_enhancement():
    e = _enhancer()
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="enhanced"))]
    )
    with patch("api.enhance.get_openai_client", return_value=client):
        e._complete("sys", "user")

    assert "response_format" not in client.chat.completions.create.call_args.kwargs
