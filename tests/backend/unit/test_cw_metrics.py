"""Tests for CloudWatch custom metrics emitter."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


@pytest.fixture(autouse=True)
def reset_metrics_module():
    """Reset the module-level client between tests."""
    import ops.metrics as m

    m._cw_client = None
    yield
    m._cw_client = None


class TestEmitRequestMetric:
    def test_calls_put_metric_data(self):
        from ops.metrics import emit_request_metric

        mock_client = MagicMock()
        with patch("ops.metrics._get_cw_client", return_value=mock_client):
            emit_request_metric("/generate", "gemini", 150.0, False)
        mock_client.put_metric_data.assert_called_once()
        call_args = mock_client.put_metric_data.call_args
        assert call_args.kwargs["Namespace"] == "PixelPrompt/Operations"

    def test_namespace_is_correct(self):
        from ops.metrics import emit_request_metric

        mock_client = MagicMock()
        with patch("ops.metrics._get_cw_client", return_value=mock_client):
            emit_request_metric("/iterate", "nova", 200.0, False)
        call_args = mock_client.put_metric_data.call_args
        assert call_args.kwargs["Namespace"] == "PixelPrompt/Operations"

    def test_dimensions_include_endpoint(self):
        from ops.metrics import emit_request_metric

        mock_client = MagicMock()
        with patch("ops.metrics._get_cw_client", return_value=mock_client):
            emit_request_metric("/generate", "gemini", 100.0, False)
        call_args = mock_client.put_metric_data.call_args
        metric_data = call_args.kwargs["MetricData"]
        # Check that at least one metric has Endpoint dimension
        found_endpoint = False
        for m in metric_data:
            for dim in m.get("Dimensions", []):
                if dim["Name"] == "Endpoint":
                    found_endpoint = True
                    break
        assert found_endpoint

    def test_dimensions_include_model_when_provided(self):
        from ops.metrics import emit_request_metric

        mock_client = MagicMock()
        with patch("ops.metrics._get_cw_client", return_value=mock_client):
            emit_request_metric("/generate", "openai", 100.0, False)
        call_args = mock_client.put_metric_data.call_args
        metric_data = call_args.kwargs["MetricData"]
        found_model = False
        for m in metric_data:
            for dim in m.get("Dimensions", []):
                if dim["Name"] == "Model":
                    found_model = True
                    assert dim["Value"] == "openai"
        assert found_model

    def test_no_model_dimension_when_none(self):
        from ops.metrics import emit_request_metric

        mock_client = MagicMock()
        with patch("ops.metrics._get_cw_client", return_value=mock_client):
            emit_request_metric("/enhance", None, 50.0, False)
        call_args = mock_client.put_metric_data.call_args
        metric_data = call_args.kwargs["MetricData"]
        for m in metric_data:
            for dim in m.get("Dimensions", []):
                assert dim["Name"] != "Model"

    def test_error_count_one_when_is_error(self):
        from ops.metrics import emit_request_metric

        mock_client = MagicMock()
        with patch("ops.metrics._get_cw_client", return_value=mock_client):
            emit_request_metric("/generate", "gemini", 100.0, True)
        call_args = mock_client.put_metric_data.call_args
        metric_data = call_args.kwargs["MetricData"]
        error_metrics = [m for m in metric_data if m["MetricName"] == "ErrorCount"]
        assert len(error_metrics) == 1
        assert error_metrics[0]["Value"] == 1

    def test_error_count_zero_when_no_error(self):
        from ops.metrics import emit_request_metric

        mock_client = MagicMock()
        with patch("ops.metrics._get_cw_client", return_value=mock_client):
            emit_request_metric("/generate", "gemini", 100.0, False)
        call_args = mock_client.put_metric_data.call_args
        metric_data = call_args.kwargs["MetricData"]
        error_metrics = [m for m in metric_data if m["MetricName"] == "ErrorCount"]
        assert len(error_metrics) == 1
        assert error_metrics[0]["Value"] == 0

    def test_errors_do_not_propagate(self):
        from ops.metrics import emit_request_metric

        mock_client = MagicMock()
        mock_client.put_metric_data.side_effect = RuntimeError("CW error")
        with patch("ops.metrics._get_cw_client", return_value=mock_client):
            # Should not raise
            emit_request_metric("/generate", "gemini", 100.0, False)

    def test_lazy_client_initialization(self):
        """Client should only be created when emit is called."""
        import ops.metrics as m

        assert m._cw_client is None
        mock_client = MagicMock()
        with patch("boto3.client", return_value=mock_client) as mock_boto:
            m.emit_request_metric("/generate", "gemini", 100.0, False)
            mock_boto.assert_called_once()
            assert mock_boto.call_args.args[0] == "cloudwatch"

        # Bounded, not botocore's 60s defaults: put_metric_data is a
        # synchronous call on the request path, so a degraded CloudWatch would
        # otherwise add minutes to a user's request while still "succeeding".
        cfg = mock_boto.call_args.kwargs["config"]
        assert cfg.connect_timeout == m._CW_TIMEOUT_SECONDS
        assert cfg.read_timeout == m._CW_TIMEOUT_SECONDS
        assert cfg.retries["total_max_attempts"] == m._CW_MAX_ATTEMPTS


class TestEmitRequestMetricsBatch:
    """One PutMetricData per generation, not one per model.

    Four sequential calls at 2s connect + 2s read x 2 attempts is up to 16s of
    blocking network time. After the async move that is no longer racing a
    gateway, but it is still 16s of a reserved concurrency slot and 16s of
    billed duration.
    """

    def _datums(self, call):
        return sorted(
            (
                m["MetricName"],
                tuple(sorted((d["Name"], d["Value"]) for d in m.get("Dimensions", []))),
                m["Value"],
            )
            for m in call.kwargs["MetricData"]
        )

    def test_four_models_emit_the_same_datums_in_one_call(self):
        """The set of datums is the contract; the number of calls is the fix."""
        from ops.metrics import emit_request_metric, emit_request_metrics

        entries = [
            ("/generate", "gemini", 100.0, False),
            ("/generate", "nova", 200.0, True),
            ("/generate", "openai", 300.0, False),
            ("/generate", "firefly", 400.0, True),
        ]

        singular = MagicMock()
        with patch("ops.metrics._get_cw_client", return_value=singular):
            for entry in entries:
                emit_request_metric(*entry)
        assert singular.put_metric_data.call_count == 4
        one_by_one = sorted(
            d for call in singular.put_metric_data.call_args_list for d in self._datums(call)
        )

        batched = MagicMock()
        with patch("ops.metrics._get_cw_client", return_value=batched):
            emit_request_metrics(entries)

        assert batched.put_metric_data.call_count == 1
        assert self._datums(batched.put_metric_data.call_args) == one_by_one

    def test_no_entries_issues_no_call(self):
        """An all-skipped generation must not pay for an empty round trip."""
        from ops.metrics import emit_request_metrics

        mock_client = MagicMock()
        with patch("ops.metrics._get_cw_client", return_value=mock_client):
            emit_request_metrics([])
        mock_client.put_metric_data.assert_not_called()

    def test_errors_do_not_propagate(self):
        from botocore.exceptions import ClientError

        from ops.metrics import emit_request_metrics

        mock_client = MagicMock()
        mock_client.put_metric_data.side_effect = ClientError(
            {"Error": {"Code": "Throttling", "Message": "slow down"}}, "PutMetricData"
        )
        with patch("ops.metrics._get_cw_client", return_value=mock_client):
            emit_request_metrics([("/generate", "gemini", 1.0, False)])

    def test_more_than_the_api_limit_is_chunked(self):
        """PutMetricData rejects more than 1,000 datums in one call.

        Four models cannot approach it. A loop that is correct for any input
        is shorter to reason about than one that is correct for four.
        """
        import ops.metrics as m

        entries = [("/generate", f"model-{i}", 1.0, False) for i in range(500)]
        mock_client = MagicMock()
        with patch("ops.metrics._get_cw_client", return_value=mock_client):
            m.emit_request_metrics(entries)

        calls = mock_client.put_metric_data.call_args_list
        assert len(calls) > 1
        assert all(len(c.kwargs["MetricData"]) <= m._CW_MAX_DATUMS_PER_CALL for c in calls)
        assert sum(len(c.kwargs["MetricData"]) for c in calls) == 4 * len(entries)

    def test_singular_still_emits_one_requests_worth(self):
        """_handle_refinement legitimately emits one; keep it working."""
        from ops.metrics import emit_request_metric

        mock_client = MagicMock()
        with patch("ops.metrics._get_cw_client", return_value=mock_client):
            emit_request_metric("/iterate", "nova", 200.0, True)

        mock_client.put_metric_data.assert_called_once()
        names = [m["MetricName"] for m in mock_client.put_metric_data.call_args.kwargs["MetricData"]]
        assert names == ["RequestCount", "ErrorCount", "Latency", "TotalErrorCount"]


def test_generate_emits_one_put_metric_data_and_skips_skipped_models():
    """The regression the batching is for, driven through run_generation.

    Skipped models never reached a provider, so counting them would report
    latency for work that did not happen -- and the skip reason is already
    carried in the response.
    """
    from unittest.mock import MagicMock, patch

    def _model(name, provider):
        m = MagicMock()
        m.name = name
        m.provider = provider
        return m

    models = [
        _model("gemini", "google_gemini"),
        _model("openai", "openai"),
        _model("firefly", "adobe_firefly"),
    ]

    mock_client = MagicMock()
    with (
        patch("ops.metrics._get_cw_client", return_value=mock_client),
        patch("lambda_function.get_enabled_models", return_value=models),
        patch("lambda_function.prompt_enhancer") as mock_enh,
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function.session_manager") as mock_sm,
        patch("lambda_function.get_handler") as mock_get_handler,
        patch("lambda_function._handle_successful_result", return_value={
            "image_key": "k", "image_url": "u"
        }),
        patch("lambda_function._cost_meter"),
        patch("lambda_function._user_repo", MagicMock()),
    ):
        mock_enh.adapt_per_model.return_value = {
            "gemini": "a cat", "openai": "a cat", "firefly": "a cat"
        }
        mock_cf.check_prompt.return_value = False
        mock_sm.add_iteration.return_value = 0
        mock_get_handler.return_value = lambda *a, **k: {
            "status": "success", "image": "aGk=", "model": "m", "provider": "google_gemini"
        }

        from lambda_function import run_generation

        run_generation({
            "sessionId": "s1",
            "prompt": "a cat",
            "modelNames": ["gemini", "openai", "firefly"],
            "skipped": {"nova": {"status": "skipped", "reason": "daily_cap_reached"}},
            "visibility": "public",
            "tier": "anon",
            "userId": "anon",
            "correlationId": "corr-batch",
        })

    assert mock_client.put_metric_data.call_count == 1
    datums = mock_client.put_metric_data.call_args.kwargs["MetricData"]
    model_dimensions = {
        d["Value"]
        for m in datums
        for d in m.get("Dimensions", [])
        if d["Name"] == "Model"
    }
    assert model_dimensions == {"gemini", "openai", "firefly"}
