"""`response()` must put retryAfter on the wire as a Retry-After header.

Five error factories compute a `retryAfter` value and `daily_spend_ceiling`
computes seconds to UTC midnight exactly, so a client can back off until the
budget actually resets. None of it reached the wire as a header, so no client
could act on it without parsing the body of a failure it may not have parsed
at all. `response()` is the single choke point every handler returns through,
so covering it covers every factory.
"""

import os
from datetime import datetime, timezone
from unittest.mock import patch

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

import lambda_function
from utils import error_responses


def test_retry_after_header_matches_the_body_value():
    body = error_responses.tier_quota_exceeded("free", 1712600000, retry_after=1800)

    resp = lambda_function.response(429, body)

    assert resp["headers"]["Retry-After"] == "1800"
    assert body["retryAfter"] == 1800


def test_rate_limit_exceeded_carries_the_header():
    resp = lambda_function.response(429, error_responses.rate_limit_exceeded(90))

    assert resp["headers"]["Retry-After"] == "90"


def test_daily_spend_ceiling_header_is_seconds_to_utc_midnight():
    frozen = datetime(2026, 7, 27, 21, 30, 0, tzinfo=timezone.utc)

    with patch("utils.error_responses.datetime") as mock_datetime:
        mock_datetime.now.return_value = frozen
        body = error_responses.daily_spend_ceiling()

    resp = lambda_function.response(503, body)

    # 21:30 UTC to midnight is 2h30m.
    assert resp["headers"]["Retry-After"] == "9000"


def test_success_response_has_no_retry_after_header():
    resp = lambda_function.response(200, {"ok": True})

    assert "Retry-After" not in resp["headers"]


def test_non_positive_retry_after_produces_no_header():
    for value in (0, -1):
        resp = lambda_function.response(429, {"error": "X", "retryAfter": value})

        assert "Retry-After" not in resp["headers"], (
            f"retryAfter={value} is not an interval a client can wait for"
        )


def test_non_integer_retry_after_produces_no_header():
    """A string or bool would render as a header value no client can parse."""
    for value in ("soon", True, None, 12.5):
        resp = lambda_function.response(429, {"error": "X", "retryAfter": value})

        assert "Retry-After" not in resp["headers"], (
            f"retryAfter={value!r} leaked a header"
        )


def test_retry_after_is_readable_cross_origin():
    """Without Expose-Headers a browser cannot read it, so emitting it is moot."""
    resp = lambda_function.response(429, error_responses.rate_limit_exceeded(60))

    assert "Retry-After" in resp["headers"]["Access-Control-Expose-Headers"]
