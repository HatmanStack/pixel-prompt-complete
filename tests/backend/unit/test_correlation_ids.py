"""Correlation-id propagation, ported from an integration suite that never ran.

``tests/backend/integration/test_correlation_ids.py`` asserted that five
endpoints answer 200 when handed an ``X-Correlation-ID`` header, and left the
part it was named for to a human: every test closed with a comment saying the
id "should be logged on backend (check CloudWatch manually)". It was skipped
on an unset ``API_ENDPOINT`` that CI never set, so it never ran -- and had it
run, a backend that discarded the header entirely would have passed all five
assertions, because none of them looked at the id.

What is asserted here instead is the observable behaviour those tests wanted:
the id a client sends is the id that appears in the structured log line for
that request, and a request that sends none still gets one.

The log entry spells the field ``correlationId`` (``utils/logger.py``), which
is why these tests read that key rather than the ``correlation_id`` keyword
the Python side passes around.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("AUTH_ENABLED", "false")

LOGGER_NAME = "pixel_prompt"


@pytest.fixture
def handler():
    """The real router, with only the AWS-touching singletons stubbed.

    ``handle_log`` is deliberately NOT patched -- it is the function that puts
    the correlation id into the log record, and patching it would leave these
    tests asserting against a mock.
    """
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        with (
            patch("lambda_function.s3_client"),
            patch("lambda_function.session_manager"),
            patch("lambda_function.image_storage"),
        ):
            from lambda_function import lambda_handler

            yield lambda_handler


def _log_event(header_name: str | None, value: str | None) -> dict:
    headers = {header_name: value} if header_name else {}
    return {
        "rawPath": "/log",
        "requestContext": {"http": {"method": "POST", "sourceIp": "1.2.3.4"}},
        "headers": headers,
        "body": json.dumps({"level": "ERROR", "message": "boom"}),
    }


def _correlation_id_of(caplog, message: str) -> str | None:
    """The id on the log record carrying ``message``.

    Keyed by message rather than "any record", because the router extracts a
    correlation id of its own and logs with it. Asserting that the id appears
    on *some* record lets either path satisfy the test and the other rot --
    verified: with the /log handler's extraction stubbed to None, an
    any-record assertion still passed.
    """
    for record in caplog.records:
        try:
            entry = json.loads(record.getMessage())
        except (TypeError, ValueError):
            continue
        if entry.get("message") == message:
            return entry.get("correlationId")
    raise AssertionError(f"no structured log record carried the message {message!r}")


@pytest.mark.parametrize("header_name", ["X-Correlation-ID", "x-correlation-id"])
def test_the_id_a_client_sends_is_the_id_that_gets_logged(handler, caplog, header_name):
    """Both spellings: API Gateway lowercases headers, browsers do not."""
    sent = "corr-" + uuid.uuid4().hex

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resp = handler(_log_event(header_name, sent), None)

    assert resp["statusCode"] == 200
    assert _correlation_id_of(caplog, "boom") == sent


def test_a_client_report_is_logged_even_without_an_id(handler, caplog):
    """Guards the test above: it would also pass if nothing were logged."""
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resp = handler(_log_event(None, None), None)

    assert resp["statusCode"] == 200
    assert _correlation_id_of(caplog, "boom") is None


def test_extract_returns_the_header_value_verbatim():
    from lambda_function import extract_correlation_id

    for header_name in ("X-Correlation-ID", "x-correlation-id"):
        event = {"headers": {header_name: "given-id"}}
        assert extract_correlation_id(event) == "given-id"


def test_a_request_without_the_header_gets_a_fresh_id():
    """The integration file called this "generated if not provided" and
    asserted only that the request returned 200."""
    from lambda_function import extract_correlation_id

    first = extract_correlation_id({"headers": {}})
    second = extract_correlation_id({})

    assert uuid.UUID(first)
    assert uuid.UUID(second)
    assert first != second
