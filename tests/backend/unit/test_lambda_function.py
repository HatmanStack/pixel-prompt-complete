"""
Unit tests for lambda_function.py — Lambda handler routing, validation, and CORS.

Mocks all module-level singletons to avoid real AWS calls.
"""

import json
from unittest.mock import MagicMock, patch

import os

import boto3
import pytest
from moto import mock_aws

# Ensure env vars are set before import
os.environ.setdefault('S3_BUCKET', 'test-bucket')
os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')
os.environ.setdefault('AWS_ACCESS_KEY_ID', 'testing')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'testing')

# Start moto mock BEFORE importing lambda_function so boto3.client('s3') succeeds.
# Must be stopped after this module's tests finish to avoid leaking moto state
# into other test files that use their own mock_aws() contexts.
_aws_mock = mock_aws()
_aws_mock.start()
_s3 = boto3.client('s3', region_name='us-east-1')
_s3.create_bucket(Bucket='test-bucket')


@pytest.fixture(autouse=True, scope="module")
def _stop_module_mock():
    """Stop the module-level moto mock after all tests in this file run."""
    yield
    _aws_mock.stop()


def _make_event(
    method="POST",
    path="/generate",
    body=None,
    headers=None,
    source_ip="1.2.3.4",
):
    event = {
        "rawPath": path,
        "requestContext": {"http": {"method": method, "sourceIp": source_ip}},
        "headers": headers or {},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _body(resp):
    return json.loads(resp["body"])


# Patch module-level singletons so importing lambda_function never hits AWS
_MOD = "lambda_function"
_TARGETS = [
    f"{_MOD}.s3_client",
    f"{_MOD}.session_manager",
    f"{_MOD}.context_manager",
    f"{_MOD}.image_storage",
    f"{_MOD}.rate_limiter",
    f"{_MOD}.content_filter",
    f"{_MOD}.prompt_enhancer",
    f"{_MOD}._executor",
    f"{_MOD}.get_enabled_models",
    f"{_MOD}.get_handler",
    f"{_MOD}.get_iterate_handler",
    f"{_MOD}.get_outpaint_handler",
    f"{_MOD}.get_model",
    f"{_MOD}.get_model_config_dict",
    f"{_MOD}.handle_log",
]


@pytest.fixture(autouse=True)
def mocks():
    patchers = []
    m = {}
    for target in _TARGETS:
        p = patch(target)
        obj = p.start()
        patchers.append(p)
        m[target.split(".")[-1]] = obj

    # Sane defaults
    m["rate_limiter"].check_rate_limit.return_value = False
    m["content_filter"].check_prompt.return_value = False
    m["get_enabled_models"].return_value = []

    yield m

    for p in patchers:
        p.stop()


from lambda_function import lambda_handler  # noqa: E402


# ============================================================
# Routing
# ============================================================


class TestRouting:
    @patch("lambda_function.as_completed")
    def test_post_generate(self, mock_as_completed, mocks):
        fake_model = MagicMock(name="flux", provider="bfl")
        fake_model.name = "flux"
        mocks["get_enabled_models"].return_value = [fake_model]
        mocks["session_manager"].create_session.return_value = "sess-1"
        mocks["get_model_config_dict"].return_value = {"id": "flux-2-pro"}

        # Create a real-looking future mock
        future = MagicMock()
        future.result.return_value = ("flux", {
            "status": "completed",
            "imageKey": "k",
            "imageUrl": "https://cdn/k",
            "iteration": 0,
            "duration": 1.0,
        })
        mocks["_executor"].submit.return_value = future
        mock_as_completed.return_value = iter([future])

        mocks["session_manager"].add_iteration.return_value = 0
        mocks["get_handler"].return_value = lambda c, p, params: {"status": "success", "image": "b64"}
        mocks["image_storage"].upload_image.return_value = "k"
        mocks["image_storage"].get_cloudfront_url.return_value = "https://cdn/k"

        resp = lambda_handler(_make_event(body={"prompt": "sunset"}), None)
        assert resp["statusCode"] == 200
        assert _body(resp)["sessionId"] == "sess-1"

    def test_post_iterate(self, mocks):
        mocks["session_manager"].get_iteration_count.return_value = 1
        mocks["session_manager"].get_latest_image_key.return_value = "k"
        mocks["session_manager"].add_iteration.return_value = 1
        mocks["image_storage"].get_image.return_value = {"output": "b64"}
        mocks["context_manager"].get_context_for_iteration.return_value = []
        mocks["get_model"].return_value = MagicMock(provider="bfl")
        mocks["get_model_config_dict"].return_value = {"id": "flux"}
        mocks["get_iterate_handler"].return_value = lambda c, s, p, ctx: {"status": "success", "image": "new"}
        mocks["image_storage"].upload_image.return_value = "k2"
        mocks["image_storage"].get_cloudfront_url.return_value = "https://cdn/k2"

        resp = lambda_handler(_make_event(path="/iterate", body={"sessionId": "s1", "model": "flux", "prompt": "more"}), None)
        assert resp["statusCode"] == 200
        assert _body(resp)["status"] == "completed"

    def test_post_outpaint(self, mocks):
        mocks["session_manager"].get_iteration_count.return_value = 0
        mocks["session_manager"].get_latest_image_key.return_value = "k"
        mocks["session_manager"].add_iteration.return_value = 1
        mocks["image_storage"].get_image.return_value = {"output": "b64"}
        mocks["get_model"].return_value = MagicMock(provider="bfl")
        mocks["get_model_config_dict"].return_value = {"id": "flux"}
        mocks["get_outpaint_handler"].return_value = lambda c, s, pr, p: {"status": "success", "image": "out"}
        mocks["image_storage"].upload_image.return_value = "k3"
        mocks["image_storage"].get_cloudfront_url.return_value = "https://cdn/k3"

        resp = lambda_handler(_make_event(path="/outpaint", body={"sessionId": "s1", "model": "flux", "preset": "16:9", "prompt": "expand"}), None)
        assert resp["statusCode"] == 200
        assert _body(resp)["preset"] == "16:9"

    def test_get_status(self, mocks):
        mocks["session_manager"].get_session.return_value = {"sessionId": "abc", "models": {}}
        resp = lambda_handler(_make_event(method="GET", path="/status/abc"), None)
        assert resp["statusCode"] == 200
        assert _body(resp)["sessionId"] == "abc"

    def test_post_enhance(self, mocks):
        mocks["prompt_enhancer"].enhance_safe.return_value = "improved prompt"
        resp = lambda_handler(_make_event(path="/enhance", body={"prompt": "sunset"}), None)
        assert resp["statusCode"] == 200
        assert _body(resp)["original"] == "sunset"

    def test_get_gallery_list(self, mocks):
        mocks["image_storage"].list_galleries.return_value = []
        resp = lambda_handler(_make_event(method="GET", path="/gallery/list"), None)
        assert resp["statusCode"] == 200
        assert "galleries" in _body(resp)

    def test_get_gallery_detail(self, mocks):
        mocks["image_storage"].list_gallery_images.return_value = []
        resp = lambda_handler(_make_event(method="GET", path="/gallery/2025-01-01"), None)
        assert resp["statusCode"] == 200
        assert _body(resp)["galleryId"] == "2025-01-01"

    def test_post_log(self, mocks):
        mocks["handle_log"].return_value = {"success": True}
        resp = lambda_handler(_make_event(path="/log", body={"level": "ERROR"}), None)
        assert resp["statusCode"] == 200


# ============================================================
# 404, OPTIONS, Rate Limiting, Content Filter, Validation
# ============================================================


class TestErrorCases:
    def test_unknown_route_404(self, mocks):
        resp = lambda_handler(_make_event(method="GET", path="/nope"), None)
        assert resp["statusCode"] == 404

    def test_wrong_method_404(self, mocks):
        resp = lambda_handler(_make_event(method="GET", path="/generate"), None)
        assert resp["statusCode"] == 404

    def test_options_cors_preflight(self, mocks):
        resp = lambda_handler(_make_event(method="OPTIONS", path="/generate"), None)
        assert resp["statusCode"] == 200
        assert _body(resp)["message"] == "CORS preflight"

    def test_rate_limit_generate(self, mocks):
        mocks["rate_limiter"].check_rate_limit.return_value = True
        resp = lambda_handler(_make_event(body={"prompt": "hi"}), None)
        assert resp["statusCode"] == 429

    def test_rate_limit_iterate(self, mocks):
        mocks["rate_limiter"].check_rate_limit.return_value = True
        resp = lambda_handler(_make_event(path="/iterate", body={"sessionId": "s", "model": "flux", "prompt": "x"}), None)
        assert resp["statusCode"] == 429

    def test_content_filter_generate(self, mocks):
        mocks["content_filter"].check_prompt.return_value = True
        resp = lambda_handler(_make_event(body={"prompt": "bad"}), None)
        assert resp["statusCode"] == 400

    def test_empty_prompt_400(self, mocks):
        resp = lambda_handler(_make_event(body={"prompt": ""}), None)
        assert resp["statusCode"] == 400

    def test_no_prompt_key_400(self, mocks):
        resp = lambda_handler(_make_event(body={}), None)
        assert resp["statusCode"] == 400

    def test_prompt_too_long_400(self, mocks):
        resp = lambda_handler(_make_event(body={"prompt": "x" * 1001}), None)
        assert resp["statusCode"] == 400

    def test_invalid_json_400(self, mocks):
        event = _make_event()
        event["body"] = "not json {"
        resp = lambda_handler(event, None)
        assert resp["statusCode"] == 400

    def test_status_not_found_404(self, mocks):
        mocks["session_manager"].get_session.return_value = None
        resp = lambda_handler(_make_event(method="GET", path="/status/missing"), None)
        assert resp["statusCode"] == 404


# ============================================================
# Stage prefix stripping
# ============================================================


class TestStagePrefixStripping:
    def test_prod_prefix(self, mocks):
        mocks["content_filter"].check_prompt.return_value = True
        resp = lambda_handler(_make_event(path="/Prod/generate", body={"prompt": "test"}), None)
        assert resp["statusCode"] == 400  # content filter, not 404

    def test_staging_prefix(self, mocks):
        mocks["session_manager"].get_session.return_value = {"sessionId": "abc", "models": {}}
        resp = lambda_handler(_make_event(method="GET", path="/Staging/status/abc"), None)
        assert resp["statusCode"] == 200


# ============================================================
# CORS headers on all responses
# ============================================================


class TestCorsHeaders:
    def _check_cors(self, resp):
        assert resp["headers"]["Access-Control-Allow-Origin"] == "*"
        assert "POST" in resp["headers"]["Access-Control-Allow-Methods"]

    def test_cors_on_200(self, mocks):
        mocks["session_manager"].get_session.return_value = {"sessionId": "s", "models": {}}
        resp = lambda_handler(_make_event(method="GET", path="/status/s"), None)
        self._check_cors(resp)

    def test_cors_on_400(self, mocks):
        resp = lambda_handler(_make_event(body={}), None)
        self._check_cors(resp)

    def test_cors_on_404(self, mocks):
        resp = lambda_handler(_make_event(method="GET", path="/nope"), None)
        self._check_cors(resp)

    def test_cors_on_429(self, mocks):
        mocks["rate_limiter"].check_rate_limit.return_value = True
        resp = lambda_handler(_make_event(body={"prompt": "hi"}), None)
        self._check_cors(resp)


# ============================================================
# Correlation ID
# ============================================================


class TestCorrelationId:
    def test_extracts_from_header(self, mocks):
        mocks["session_manager"].get_session.return_value = {"sessionId": "s", "models": {}}
        resp = lambda_handler(_make_event(method="GET", path="/status/s", headers={"x-correlation-id": "corr-123"}), None)
        assert resp["statusCode"] == 200

    def test_generates_when_missing(self, mocks):
        mocks["session_manager"].get_session.return_value = {"sessionId": "s", "models": {}}
        resp = lambda_handler(_make_event(method="GET", path="/status/s"), None)
        assert resp["statusCode"] == 200
