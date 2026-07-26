"""Tests for spend and quota-rejection metrics.

Spend lives in DynamoDB and shows on the admin dashboard; rejections lived
nowhere at all. Neither of those can page anyone — these metrics are what
make a runaway bill or a rejection spike something an operator hears about
rather than discovers later.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFRONT_DOMAIN", "test.cloudfront.net")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


@pytest.fixture(autouse=True)
def _reset_client():
    import ops.metrics as m

    m._cw_client = None
    yield
    m._cw_client = None


def _metrics(mock_client):
    """Flatten every MetricName -> value emitted."""
    out = {}
    for call in mock_client.put_metric_data.call_args_list:
        for md in call.kwargs["MetricData"]:
            out[md["MetricName"]] = md
    return out


def test_spend_is_emitted_in_dollars_not_micros():
    """An alarm threshold a human sets should read 50, not 50000000."""
    from ops.metrics import emit_spend_metric

    client = MagicMock()
    with patch("ops.metrics._get_cw_client", return_value=client):
        emit_spend_metric(250_000, "paid")  # $0.25

    md = _metrics(client)
    assert md["TotalSpendUsd"]["Value"] == 0.25
    assert md["SpendUsd"]["Value"] == 0.25


def test_spend_carries_an_undimensioned_total():
    """A CloudWatch alarm cannot sum across dimension values.

    Without a separate undimensioned series, an alarm on total spend would
    silently only ever see one tier.
    """
    from ops.metrics import emit_spend_metric

    client = MagicMock()
    with patch("ops.metrics._get_cw_client", return_value=client):
        emit_spend_metric(100_000, "free")

    md = _metrics(client)
    assert "Dimensions" not in md["TotalSpendUsd"]
    assert md["SpendUsd"]["Dimensions"] == [{"Name": "Tier", "Value": "free"}]


def test_free_tier_spend_is_separable():
    """Free-tier spend is pure acquisition cost and alarmed separately."""
    from ops.metrics import emit_spend_metric

    client = MagicMock()
    with patch("ops.metrics._get_cw_client", return_value=client):
        emit_spend_metric(100_000, "free")

    assert _metrics(client)["SpendUsd"]["Dimensions"][0]["Value"] == "free"


def test_zero_spend_is_not_emitted():
    from ops.metrics import emit_spend_metric

    client = MagicMock()
    with patch("ops.metrics._get_cw_client", return_value=client):
        emit_spend_metric(0, "paid")
    client.put_metric_data.assert_not_called()


def test_spend_metric_failure_never_raises():
    """Telemetry must not fail the request it is describing."""
    from ops.metrics import emit_spend_metric

    client = MagicMock()
    client.put_metric_data.side_effect = RuntimeError("cloudwatch down")
    with patch("ops.metrics._get_cw_client", return_value=client):
        emit_spend_metric(100, "paid")  # must not raise


def test_quota_rejection_records_the_reason():
    """Abuse and a badly-set limit look identical without the reason."""
    from ops.metrics import emit_quota_rejection

    client = MagicMock()
    with patch("ops.metrics._get_cw_client", return_value=client):
        emit_quota_rejection("guest", "generate", "guest_ip")

    dims = {d["Name"]: d["Value"] for d in _metrics(client)["QuotaRejection"]["Dimensions"]}
    assert dims == {"Tier": "guest", "Endpoint": "generate", "Reason": "guest_ip"}


def test_quota_rejection_failure_never_raises():
    from ops.metrics import emit_quota_rejection

    client = MagicMock()
    client.put_metric_data.side_effect = RuntimeError("down")
    with patch("ops.metrics._get_cw_client", return_value=client):
        emit_quota_rejection("free", "generate", "free_generate")


def test_cost_meter_mirrors_spend_to_cloudwatch():
    """DynamoDB holds the authoritative number; CloudWatch is what alarms."""
    import boto3
    from moto import mock_aws

    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="obs-test",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        from ops.cost_meter import CostMeter
        from users.repository import UserRepository

        meter = CostMeter(UserRepository("obs-test", dynamodb_resource=ddb))
        with patch("ops.metrics.emit_spend_metric") as mock_emit:
            meter.record(costs={"gemini": 39000}, tier="paid", now=1784980800)
        mock_emit.assert_called_once_with(39000, "paid")


def test_cloudwatch_failure_does_not_break_metering():
    """A telemetry outage must not stop spend being recorded in DynamoDB."""
    import boto3
    from moto import mock_aws

    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="obs-test2",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        from ops.cost_meter import CostMeter
        from users.repository import UserRepository

        repo = UserRepository("obs-test2", dynamodb_resource=ddb)
        meter = CostMeter(repo)
        with patch(
            "ops.metrics.emit_spend_metric", side_effect=RuntimeError("cw down")
        ):
            total = meter.record(costs={"gemini": 39000}, tier="paid", now=1784980800)

        assert total == 39000
        assert meter.get_daily_spend(now=1784980800)["totalMicros"] == 39000


def test_quota_denial_emits_a_rejection_metric():
    """End to end: a denied request produces the signal."""
    import lambda_function
    from users.quota import QuotaResult

    denied = QuotaResult(allowed=False, reason="anon_generate", reset_at=1, usage={})
    with (
        patch("config.auth_enabled", False),
        patch("lambda_function._daily_spend_exceeded", return_value=False),
        patch("lambda_function.content_filter") as mock_cf,
        patch("lambda_function._enforce_quota_safe", return_value=denied),
        patch("lambda_function.emit_quota_rejection") as mock_emit,
    ):
        mock_cf.check_prompt.return_value = False
        lambda_function._parse_and_validate_request(
            {
                "body": json.dumps({"prompt": "a cat"}),
                "requestContext": {"http": {"sourceIp": "1.2.3.4", "method": "POST"}},
                "headers": {},
            },
            require_prompt=True,
            endpoint_kind="generate",
        )

    mock_emit.assert_called_once()
    assert mock_emit.call_args.args[2] == "anon_generate"
