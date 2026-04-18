"""
Tests for generate endpoint resilience — future.result() error handling and timeouts.
"""

import json
from concurrent.futures import TimeoutError
from unittest.mock import MagicMock, patch

import os

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

_MOD = "lambda_function"
_TARGETS = [
    f"{_MOD}.s3_client",
    f"{_MOD}.session_manager",
    f"{_MOD}.context_manager",
    f"{_MOD}.image_storage",
    f"{_MOD}.content_filter",
    f"{_MOD}.prompt_enhancer",
    f"{_MOD}._executor",
    f"{_MOD}._gallery_executor",
    f"{_MOD}.get_enabled_models",
    f"{_MOD}.get_handler",
    f"{_MOD}.get_iterate_handler",
    f"{_MOD}.get_outpaint_handler",
    f"{_MOD}.get_model",
    f"{_MOD}.get_model_config_dict",
    f"{_MOD}.handle_log",
]


def _make_event(method="POST", path="/generate", body=None, source_ip="1.2.3.4"):
    event = {
        "rawPath": path,
        "requestContext": {"http": {"method": method, "sourceIp": source_ip}},
        "headers": {},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _body(resp):
    return json.loads(resp["body"])


@pytest.fixture(autouse=True)
def mocks():
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        patchers = []
        m = {}
        for target in _TARGETS:
            p = patch(target)
            obj = p.start()
            patchers.append(p)
            m[target.split(".")[-1]] = obj

        m["content_filter"].check_prompt.return_value = False
        m["get_enabled_models"].return_value = []
        yield m
        for p in patchers:
            p.stop()


def _get_lambda_handler():
    from lambda_function import lambda_handler

    return lambda_handler


def _setup_two_models(mocks):
    """Set up two fake models (gemini and nova) for generation tests."""
    gemini = MagicMock()
    gemini.name = "gemini"
    gemini.provider = "google_gemini"
    nova = MagicMock()
    nova.name = "nova"
    nova.provider = "bedrock_nova"
    mocks["get_enabled_models"].return_value = [gemini, nova]
    mocks["session_manager"].create_session.return_value = "sess-1"
    mocks["get_model_config_dict"].return_value = {"id": "test-model"}
    mocks["session_manager"].add_iteration.return_value = 0
    mocks["get_handler"].return_value = lambda c, p, params: {"status": "success", "image": "b64"}
    mocks["image_storage"].upload_image.return_value = "k"
    mocks["image_storage"].get_cloudfront_url.return_value = "https://cdn/k"
    return gemini, nova


class TestFutureResultResilience:
    @patch("lambda_function.as_completed")
    def test_single_future_failure_returns_partial_results(self, mock_as_completed, mocks):
        """When one model's future raises, other models should still succeed."""
        lambda_handler = _get_lambda_handler()
        gemini, nova = _setup_two_models(mocks)

        # gemini future succeeds
        good_future = MagicMock()
        good_future.result.return_value = (
            "gemini",
            {"status": "completed", "imageKey": "k", "imageUrl": "u", "iteration": 0, "duration": 1.0},
        )

        # nova future raises
        bad_future = MagicMock()
        bad_future.result.side_effect = RuntimeError("Provider crashed")

        # Map futures to models for the futures dict
        mocks["_executor"].submit.side_effect = [good_future, bad_future]
        mock_as_completed.return_value = iter([good_future, bad_future])

        resp = lambda_handler(_make_event(body={"prompt": "sunset"}), None)
        assert resp["statusCode"] == 200
        body = _body(resp)
        assert body["models"]["gemini"]["status"] == "completed"
        assert body["models"]["nova"]["status"] == "error"

    @patch("lambda_function.as_completed")
    def test_future_timeout_produces_error_results(self, mock_as_completed, mocks):
        """When as_completed times out, remaining models get timeout errors."""
        lambda_handler = _get_lambda_handler()
        gemini, nova = _setup_two_models(mocks)

        # Only gemini completes before timeout
        good_future = MagicMock()
        good_future.result.return_value = (
            "gemini",
            {"status": "completed", "imageKey": "k", "imageUrl": "u", "iteration": 0, "duration": 1.0},
        )

        # nova never completes - as_completed raises TimeoutError after yielding gemini
        pending_future = MagicMock()
        mocks["_executor"].submit.side_effect = [good_future, pending_future]

        def _as_completed_with_timeout(*args, **kwargs):
            yield good_future
            raise TimeoutError("futures timed out")

        mock_as_completed.side_effect = _as_completed_with_timeout

        resp = lambda_handler(_make_event(body={"prompt": "sunset"}), None)
        assert resp["statusCode"] == 200
        body = _body(resp)
        assert body["models"]["gemini"]["status"] == "completed"
        assert body["models"]["nova"]["status"] == "error"
        assert "timed out" in body["models"]["nova"]["error"].lower()

    @patch("lambda_function.as_completed")
    def test_all_futures_fail_returns_all_errors(self, mock_as_completed, mocks):
        """When all futures fail, all models should have error results."""
        lambda_handler = _get_lambda_handler()
        gemini, nova = _setup_two_models(mocks)

        bad1 = MagicMock()
        bad1.result.side_effect = RuntimeError("Error 1")
        bad2 = MagicMock()
        bad2.result.side_effect = RuntimeError("Error 2")

        mocks["_executor"].submit.side_effect = [bad1, bad2]
        mock_as_completed.return_value = iter([bad1, bad2])

        resp = lambda_handler(_make_event(body={"prompt": "sunset"}), None)
        assert resp["statusCode"] == 200
        body = _body(resp)
        assert body["models"]["gemini"]["status"] == "error"
        assert body["models"]["nova"]["status"] == "error"


class TestThreadPoolLifecycle:
    def test_shutdown_executors_calls_shutdown_on_both_pools(self, mocks):
        """_shutdown_executors should call shutdown(wait=False) on both executors."""
        from lambda_function import _shutdown_executors

        mock_exec = MagicMock()
        mock_gallery_exec = MagicMock()

        with patch("lambda_function._executor", mock_exec), patch(
            "lambda_function._gallery_executor", mock_gallery_exec
        ):
            _shutdown_executors()

        mock_exec.shutdown.assert_called_once_with(wait=False)
        mock_gallery_exec.shutdown.assert_called_once_with(wait=False)

    def test_atexit_is_registered(self, mocks):
        """atexit should have _shutdown_executors registered."""
        import importlib

        with patch("atexit.register") as mock_register:
            importlib.reload(__import__("lambda_function"))

        registered_funcs = [call.args[0].__name__ for call in mock_register.call_args_list]
        assert "_shutdown_executors" in registered_funcs
