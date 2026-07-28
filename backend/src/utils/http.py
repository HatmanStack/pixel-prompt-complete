"""The single API Gateway response builder.

There were six of these -- ``lambda_function.response`` plus a private
``_response`` in each of ``admin/auth``, ``admin/users``, ``admin/models``,
``admin/metrics``, ``billing/checkout``, ``billing/portal`` and
``billing/webhook`` -- and they had already diverged in two ways that reached
users:

* ``lambda_function.response`` paired ``Access-Control-Allow-Origin: *`` with
  ``Access-Control-Allow-Credentials: true``, which the CORS spec forbids.
* ``admin/auth._response`` sent no CORS headers at all, so every admin
  rejection arrived at the browser as an opaque CORS failure instead of the
  401, 403 or 501 it actually was.

Both are the same defect: header policy expressed in more than one place. One
builder is the fix, and ``tests/backend/unit/test_cors_headers.py`` fails if a
seventh appears.

Note on the deployed path (ADR-A9): when the HttpApi ``CorsConfiguration`` is
present, API Gateway overrides integration CORS headers, so what a browser
sees in production comes from the gateway. These headers are still what
``sam local start-api`` and any direct invocation return, and they have to be
correct on their own.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import config

# ``Access-Control-Allow-Credentials`` is omitted when the allowed origin is
# "*". The spec forbids the pair and browsers reject the response outright --
# so emitting both does not loosen CORS, it breaks it, and it breaks it for
# the one client that sends ``credentials: 'include'``. The config warning at
# config.py's CORS check only fires when auth_enabled, which is exactly the
# case where an operator has already thought about the origin.
_CREDENTIALS_HEADER = "Access-Control-Allow-Credentials"
_WILDCARD_ORIGIN = "*"


def cors_headers() -> dict[str, str]:
    """The CORS header set every HTTP response carries.

    ``config.cors_allowed_origin`` is read here rather than captured at import
    so a reload or a test override takes effect. The old module-level
    ``from config import cors_allowed_origin`` meant the value was frozen into
    whichever module imported it first.
    """
    headers = {
        "Access-Control-Allow-Origin": config.cors_allowed_origin,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": (
            "Content-Type, Authorization, X-Requested-With, X-Correlation-ID"
        ),
        # Without this a browser cannot read Retry-After cross-origin, which
        # would make emitting it pointless for the only client that has one.
        # Only headers a response actually carries. Retry-After is set on
        # the 429 paths and tested. X-Correlation-ID was listed here
        # too, but nothing sets it on a response: the client mints its
        # own and sends it (client.ts), and the server only ever reads
        # it off the request. Advertising a header that is never
        # present tells a browser to expose nothing and tells the next
        # reader the wrong thing about the contract.
        "Access-Control-Expose-Headers": "Retry-After",
    }
    if config.cors_allowed_origin != _WILDCARD_ORIGIN:
        headers[_CREDENTIALS_HEADER] = "true"
    return headers


def json_response(
    status_code: int,
    body: dict[str, Any],
    set_cookie: str | None = None,
    *,
    default: Callable[[Any], Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build an API Gateway HTTP response.

    ``retryAfter`` in the body is mirrored into a real ``Retry-After`` header.
    Mirroring here rather than at each call site means any response that
    carries the field gets the header; it does not put the field there. Only a
    caller that knows when the limit lifts can do that -- the quota rejections
    in ``_parse_and_validate_request`` and ``daily_spend_ceiling``, which
    computes seconds to UTC midnight. ``model_cost_ceiling`` deliberately has
    no interval: ``consume_model_slot`` returns a bare bool, so its reset is
    not in scope at the point of refusal, and a guess would be worse than
    silence.

    The body field stays: a client already reading it must keep working, and
    the two agreeing is the point.

    Args:
        default: JSON encoder fallback. ``admin/metrics`` needs one for
            DynamoDB ``Decimal`` values and ``admin/users`` for arbitrary item
            attributes; losing it would turn every such response into a 500.
        extra_headers: Response-specific headers, e.g. ``/pricing``'s
            ``Cache-Control``. Applied after the CORS set so a caller cannot
            silently drop a CORS header by colliding with it -- it can only
            override deliberately, which is visible at the call site.
    """
    headers = {"Content-Type": "application/json", **cors_headers()}
    if extra_headers:
        headers.update(extra_headers)

    retry_after = body.get("retryAfter") if isinstance(body, dict) else None
    # bool is an int subclass, and True would render as "True" -- a value no
    # client can parse into a delay.
    if isinstance(retry_after, int) and not isinstance(retry_after, bool) and retry_after > 0:
        headers["Retry-After"] = str(retry_after)

    resp: dict[str, Any] = {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, default=default),
    }
    if set_cookie:
        resp["cookies"] = [set_cookie]
    return resp


def invocation_ack(body: str | None = None) -> dict[str, Any]:
    """Acknowledge a Lambda invocation that is not an HTTP request.

    The EventBridge daily snapshot and the ``/generate`` worker are invoked
    directly, not through the gateway: nothing reads response headers on
    either, and a CORS header there would be noise pretending to be policy.
    They still return a status-shaped dict because that is the Lambda
    convention and it makes a failed invocation legible in the logs.

    It lives here so ``grep '"statusCode"' backend/src/`` has exactly one
    answer. The moment response construction is spread across two files, one
    of them drifts -- which is the whole history this module is fixing.
    """
    ack: dict[str, Any] = {"statusCode": 200}
    if body is not None:
        ack["body"] = body
    return ack
