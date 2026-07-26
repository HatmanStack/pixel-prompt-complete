"""Tests that no provider can outlive the dispatch budget.

handle_generate's timeout cannot cancel a future that has already started:
the provider call is blocking I/O inside a worker thread. So the budget is
only meaningful if every provider bounds its own call below it. Otherwise the
request is abandoned, the user is told the model failed, and the provider
generates and bills for the image anyway.

Nova was unbounded until this change, using botocore's defaults of 60s
connect plus 60s read with legacy retries.
"""

from __future__ import annotations

import os

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFRONT_DOMAIN", "test.cloudfront.net")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


def test_bedrock_client_has_bounded_timeouts():
    import utils.clients as c

    c._bedrock_clients.clear()
    cfg = c.get_bedrock_client().meta.config
    assert cfg.read_timeout is not None, "Nova would use botocore's 60s default"
    assert cfg.connect_timeout is not None


def test_nova_worst_case_fits_inside_the_dispatch_budget():
    """Including retries. One slow attempt plus a retry must still fit."""
    import config
    import utils.clients as c

    c._bedrock_clients.clear()
    cfg = c.get_bedrock_client().meta.config
    worst_case = cfg.read_timeout * cfg.retries["total_max_attempts"]
    assert worst_case <= config.generate_dispatch_budget_seconds, (
        f"Nova can run {worst_case}s against a "
        f"{config.generate_dispatch_budget_seconds}s budget"
    )


def test_retries_are_capped():
    """Unbounded retries would multiply the timeout past any budget."""
    import utils.clients as c

    c._bedrock_clients.clear()
    cfg = c.get_bedrock_client().meta.config
    assert cfg.retries["total_max_attempts"] <= 2


def test_gemini_client_passes_a_timeout():
    import utils.clients as c

    c._genai_clients.clear()
    client = c.get_genai_client("k", timeout=30.0)
    assert client is not None
    # A distinct cache entry per timeout, so an untimed client cannot be
    # returned to a caller that asked for one.
    assert ("k", 30.0) in c._genai_clients


def test_dispatch_budget_exceeds_the_client_timeout():
    """The budget must be the outer bound, not the inner one."""
    import config

    assert config.generate_dispatch_budget_seconds > config.api_client_timeout


def test_bedrock_client_is_cached_per_region():
    import utils.clients as c

    c._bedrock_clients.clear()
    a = c.get_bedrock_client("us-west-2")
    b = c.get_bedrock_client("us-west-2")
    assert a is b
    assert c.get_bedrock_client("eu-west-1") is not a
