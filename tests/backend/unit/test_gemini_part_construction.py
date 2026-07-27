"""Gemini refinement builds its prompt part against the real SDK signature.

``google.genai`` declares ``types.Part.from_text(*, text: str)`` -- keyword
only. ``iterate_gemini`` and ``outpaint_gemini`` called it positionally, so
both raised ``TypeError`` at runtime, had it swallowed by their own ``except``
and returned an error result. Gemini refinement was broken in the deployed
stack while the whole suite stayed green.

It stayed green because every existing Gemini test patches
``models.providers.gemini.types`` wholesale (``test_iterate_handlers.py``,
``test_gemini_handler.py``). A ``Mock`` accepts any call shape, so the one
thing that was wrong was the one thing no test could see.

**These tests therefore do not patch ``types``.** They patch the client and
nothing else, so the real ``Part`` constructors run. That is the entire point
of the file, and a future edit that adds a ``types`` patch here removes its
reason to exist.
"""

from __future__ import annotations

import base64
import inspect
from unittest.mock import Mock, patch

import pytest
from google.genai import types

from models.providers.gemini import iterate_gemini, outpaint_gemini

_PIXEL = b"\x89PNG\r\n\x1a\n-not-a-real-png"
_SOURCE = base64.b64encode(_PIXEL).decode()

_CONFIG = {
    "provider": "google_gemini",
    "id": "gemini-3.1-flash-image-preview",
    "api_key": "test-key",
}


def _client_returning_an_image():
    """A Gemini client that answers with one inline image part."""
    part = Mock()
    part.inline_data = Mock()
    part.inline_data.data = _PIXEL

    candidate = Mock()
    candidate.content.parts = [part]

    response = Mock()
    response.candidates = [candidate]

    client = Mock()
    client.models.generate_content.return_value = response
    return client


def test_from_text_is_keyword_only_or_this_file_proves_nothing():
    """The guard that stops these tests passing vacuously.

    If the SDK ever accepts a positional ``text`` again, the two tests below
    would pass against the defect they exist to catch. This says so out loud
    instead of letting them quietly stop meaning anything.
    """
    params = inspect.signature(types.Part.from_text).parameters
    assert params["text"].kind is inspect.Parameter.KEYWORD_ONLY, (
        "google.genai now accepts a positional text; the tests below no "
        "longer distinguish the fix from the defect"
    )


@pytest.mark.parametrize(
    "call,expected_text",
    [
        (
            lambda: iterate_gemini(_CONFIG, _SOURCE, "add a river", []),
            "Edit this image: add a river",
        ),
        (
            lambda: outpaint_gemini(_CONFIG, _SOURCE, "16:9", "more sky"),
            "more sky",
        ),
    ],
    ids=["iterate", "outpaint"],
)
def test_refinement_reaches_the_provider_with_a_real_text_part(call, expected_text):
    """Success, not "did not raise": the handler catches TypeError itself.

    Asserting the returned status alone would still pass against a handler
    that failed for some other reason, so this also reads the Part that
    actually reached generate_content and checks the prompt is in it.
    """
    client = _client_returning_an_image()
    with patch("models.providers.gemini._get_genai_client", return_value=client):
        result = call()

    assert result["status"] == "success", result

    contents = client.models.generate_content.call_args.kwargs["contents"]
    text_parts = [p for p in contents if isinstance(p, types.Part) and p.text]
    assert text_parts, contents
    assert expected_text in (text_parts[0].text or "")
