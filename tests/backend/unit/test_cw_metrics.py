"""Tests for CloudWatch custom metrics emitter."""

from __future__ import annotations

import importlib
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
            mock_boto.assert_called_once_with("cloudwatch")
