"""The /enhance prompt ceiling, ported from an integration suite that never ran.

``tests/backend/integration/test_api_endpoints.py`` asserted that a 501-character
prompt is rejected by ``/enhance``. Everything else in that file is covered by
unit tests -- 404 routing, CORS headers, gallery list and detail, the /generate
validation trio -- but this ceiling was not: ``handle_enhance`` passes
``max_prompt_length=500`` (``lambda_function.py:1942``) while every existing
length test drives ``/generate``, whose limit is 1000. Delete the integration
file without porting this and the 500 becomes unguarded.

The boundary is asserted from both sides. A test that only checks 501 -> 400
passes just as well against a handler that rejects everything.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("AUTH_ENABLED", "false")


@pytest.fixture
def handler():
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        with (
            patch("lambda_function.s3_client"),
            patch("lambda_function.session_manager"),
            patch("lambda_function.image_storage"),
            patch("lambda_function.content_filter") as content_filter,
            patch("lambda_function.prompt_enhancer") as enhancer,
        ):
            content_filter.check_prompt.return_value = False
            enhancer.enhance_variants.return_value = ("short", "long")
            from lambda_function import lambda_handler

            yield lambda_handler


def _enhance(prompt: str) -> dict:
    return {
        "rawPath": "/enhance",
        "requestContext": {"http": {"method": "POST", "sourceIp": "1.2.3.4"}},
        "headers": {},
        "body": json.dumps({"prompt": prompt}),
    }


def test_a_prompt_at_the_ceiling_is_accepted(handler):
    resp = handler(_enhance("a" * 500), None)
    assert resp["statusCode"] == 200


def test_a_prompt_one_character_over_the_ceiling_is_rejected(handler):
    resp = handler(_enhance("a" * 501), None)
    assert resp["statusCode"] == 400
    assert "error" in json.loads(resp["body"])
