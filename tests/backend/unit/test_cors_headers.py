"""One CORS header builder, and never a wildcard origin with credentials.

Two defects motivated this module. ``lambda_function.response`` paired
``Access-Control-Allow-Origin: *`` -- the default -- with
``Access-Control-Allow-Credentials: true``, a combination the CORS spec
forbids and browsers reject outright, while ``frontend/src/api/client.ts``
sends ``credentials: 'include'``. And ``admin/auth.py`` sent no CORS headers
at all, so every admin rejection (501 disabled, 401 unauthenticated, 403
not-an-admin) reached the browser as an opaque CORS failure with no status.

The table-driven tests here are the part that lasts. Six divergent response
builders existed; asserting that every one produces the same header key set,
and that no seventh appears, is what stops them diverging again.
"""

from __future__ import annotations

import importlib
import json
import os
import pathlib
import re

import pytest

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFRONT_DOMAIN", "test.cloudfront.net")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

_SRC = pathlib.Path(__file__).resolve().parents[3] / "backend" / "src"


def _builders():
    """Every (name, callable(status, body) -> response) in backend/src."""
    import admin.auth
    import admin.metrics
    import admin.models
    import admin.users
    import billing.checkout
    import billing.portal
    import billing.webhook
    import lambda_function
    import utils.http

    return [
        ("utils.http.json_response", utils.http.json_response),
        ("lambda_function.response", lambda_function.response),
        ("admin.auth._response", admin.auth._response),
        ("admin.users._response", admin.users._response),
        ("admin.models._response", admin.models._response),
        ("admin.metrics._response", admin.metrics._response),
        ("billing.checkout._response", billing.checkout._response),
        ("billing.portal._response", billing.portal._response),
        ("billing.webhook._response", billing.webhook._response),
    ]


@pytest.fixture
def named_origin():
    """Reload config with a real origin, then put it back."""
    import config

    previous = os.environ.get("CORS_ALLOWED_ORIGIN")
    os.environ["CORS_ALLOWED_ORIGIN"] = "https://example.com"
    try:
        yield importlib.reload(config)
    finally:
        if previous is None:
            os.environ.pop("CORS_ALLOWED_ORIGIN", None)
        else:
            os.environ["CORS_ALLOWED_ORIGIN"] = previous
        importlib.reload(config)


class TestOneBuilder:
    def test_only_utils_http_constructs_a_response(self):
        """A seventh builder is the failure this test exists to prevent.

        Six divergent ones is how admin/auth.py came to send no CORS headers
        while lambda_function.py sent a spec-violating pair.
        """
        offenders = []
        for path in sorted(_SRC.rglob("*.py")):
            if path.name == "http.py" and path.parent.name == "utils":
                continue
            if re.search(r'"statusCode"\s*:', path.read_text()):
                offenders.append(str(path.relative_to(_SRC)))
        assert not offenders, (
            f"response construction outside utils/http.py: {offenders}"
        )

    @pytest.mark.parametrize(
        "name,builder", _builders(), ids=lambda v: v if isinstance(v, str) else ""
    )
    def test_every_builder_produces_the_same_header_keys(self, name, builder):
        import utils.http

        expected = set(utils.http.json_response(200, {})["headers"])
        assert set(builder(200, {})["headers"]) == expected, name

    @pytest.mark.parametrize(
        "name,builder", _builders(), ids=lambda v: v if isinstance(v, str) else ""
    )
    def test_every_builder_carries_the_origin(self, name, builder):
        resp = builder(403, {"error": "no"})
        assert "Access-Control-Allow-Origin" in resp["headers"], name
        assert resp["statusCode"] == 403
        assert json.loads(resp["body"]) == {"error": "no"}


class TestWildcardAndCredentials:
    def test_wildcard_origin_omits_the_credentials_header(self):
        """The spec forbids the pair; a browser rejects the whole response.

        Emitting both does not loosen CORS, it breaks it.
        """
        import config
        import utils.http

        assert config.cors_allowed_origin == "*"
        headers = utils.http.cors_headers()
        assert headers["Access-Control-Allow-Origin"] == "*"
        assert "Access-Control-Allow-Credentials" not in headers

    def test_named_origin_carries_the_credentials_header(self, named_origin):
        """A real origin is exactly the case where the client needs cookies."""
        import utils.http

        headers = utils.http.cors_headers()
        assert headers["Access-Control-Allow-Origin"] == "https://example.com"
        assert headers["Access-Control-Allow-Credentials"] == "true"

    def test_no_builder_ever_pairs_a_wildcard_with_credentials(self):
        for name, builder in _builders():
            headers = builder(200, {})["headers"]
            if headers.get("Access-Control-Allow-Origin") == "*":
                assert "Access-Control-Allow-Credentials" not in headers, name


class TestAdminRejectionsReachTheBrowser:
    def test_a_non_admin_gets_403_with_cors_headers(self):
        """The difference between the UI showing "403 Forbidden" and showing
        a CORS error with no status at all."""
        import config
        from admin.auth import require_admin_request

        event = {
            "requestContext": {
                "authorizer": {
                    "jwt": {"claims": {"sub": "u1", "cognito:groups": "users"}}
                }
            }
        }
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(config, "admin_enabled", True)
            mp.setattr(config, "auth_enabled", True)
            claims, err = require_admin_request(event)

        assert claims is None
        assert err["statusCode"] == 403
        assert "Access-Control-Allow-Origin" in err["headers"]

    def test_an_admin_403_carries_the_same_cors_headers_as_a_generate_200(self):
        import config
        import lambda_function
        from admin.auth import require_admin_request

        event = {
            "requestContext": {
                "authorizer": {
                    "jwt": {"claims": {"sub": "u1", "cognito:groups": "users"}}
                }
            }
        }
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(config, "admin_enabled", True)
            mp.setattr(config, "auth_enabled", True)
            _, err = require_admin_request(event)

        ok = lambda_function.response(200, {"sessionId": "s"})
        cors = {
            k: v for k, v in ok["headers"].items() if k.startswith("Access-Control")
        }
        assert {
            k: v for k, v in err["headers"].items() if k.startswith("Access-Control")
        } == cors

    def test_admin_disabled_501_also_carries_cors(self):
        """501 is the response an operator sees most often while wiring the
        dashboard up, so it is the one that must not look like a CORS bug."""
        import config
        from admin.auth import require_admin_request

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(config, "admin_enabled", False)
            _, err = require_admin_request({})

        assert err["statusCode"] == 501
        assert "Access-Control-Allow-Origin" in err["headers"]


class TestSharedBuilderKeepsItsExistingBehaviour:
    def test_retry_after_is_still_mirrored_from_the_body(self):
        import utils.http

        resp = utils.http.json_response(429, {"error": "slow down", "retryAfter": 42})
        assert resp["headers"]["Retry-After"] == "42"
        assert "Retry-After" in resp["headers"]["Access-Control-Expose-Headers"]

    def test_a_boolean_retry_after_is_not_mirrored(self):
        """bool is an int subclass and True would render as "True"."""
        import utils.http

        resp = utils.http.json_response(429, {"retryAfter": True})
        assert "Retry-After" not in resp["headers"]

    def test_set_cookie_still_becomes_the_cookies_list(self):
        import utils.http

        resp = utils.http.json_response(200, {}, set_cookie="g=1; HttpOnly")
        assert resp["cookies"] == ["g=1; HttpOnly"]

    def test_a_custom_json_encoder_is_honoured(self):
        """admin/metrics.py serialises DynamoDB Decimals; convergence must not
        lose that or every admin metrics response becomes a 500."""
        from decimal import Decimal

        import utils.http

        resp = utils.http.json_response(200, {"n": Decimal(3)}, default=str)
        assert json.loads(resp["body"]) == {"n": "3"}
