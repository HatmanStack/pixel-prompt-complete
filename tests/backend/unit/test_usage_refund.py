"""Refunds must reach the call-counting quota, not only the credit ledger.

What these tests prove: ``UserRepository.decrement_counter`` gives a unit back
only when the window that consumed it is still the current one, and
``lambda_function._refund_usage`` picks the right counter for the tier and
endpoint that ``users.quota.enforce_quota`` incremented. The end-to-end case
drives a real ``/generate`` through ``lambda_handler`` against moto DynamoDB
with the real ``UserRepository`` and the real ``enforce_quota``, with
``CREDITS_ENABLED`` at its shipped default of false -- the configuration in
which the whole refund path used to be inert.

What they cannot prove: that a concurrent refund and increment interleave
correctly. That is DynamoDB's conditional write, exercised here single-threaded
against moto. See ADR-A8 for why ``CREDITS_ENABLED`` is not simply defaulted on.
"""

from __future__ import annotations

import importlib
import json
import os
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

from users.tier import TierContext

_TABLE = "pixel-prompt-users"
_NOW = 1_700_000_000


def _make_table(ddb):
    ddb.create_table(
        TableName=_TABLE,
        KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


@pytest.fixture
def repo():
    """The real repository over moto DynamoDB, single-threaded."""
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        _make_table(ddb)
        from users.repository import UserRepository

        yield UserRepository(_TABLE, dynamodb_resource=ddb)


def _seed(repo, user_id, **fields):
    item = {"userId": user_id}
    item.update(fields)
    repo._table.put_item(Item=item)


def _counter(repo, user_id, name):
    item = repo.get_user(user_id) or {}
    return int(item.get(name, 0) or 0)


# --------------------------------------------------------------------------
# decrement_counter
# --------------------------------------------------------------------------


def test_decrement_returns_a_consumed_unit_inside_the_window(repo):
    _seed(repo, "u1", generateCount=1, windowStart=_NOW - 10)

    assert (
        repo.decrement_counter("u1", "generateCount", "windowStart", 3600, _NOW) is True
    )
    assert _counter(repo, "u1", "generateCount") == 0


def test_decrement_leaves_a_zero_counter_alone_without_raising(repo):
    _seed(repo, "u1", generateCount=0, windowStart=_NOW - 10)

    assert (
        repo.decrement_counter("u1", "generateCount", "windowStart", 3600, _NOW)
        is False
    )
    assert _counter(repo, "u1", "generateCount") == 0


def test_decrement_does_not_refund_into_a_window_that_already_reset(repo):
    """The load-bearing condition.

    A window that has rolled over has already given the caller a fresh
    allowance. Decrementing then would take the counter negative in the NEW
    window, which is a free extra call on top of the one they were just
    granted -- the exact opposite of making them whole.
    """
    _seed(repo, "u1", generateCount=1, windowStart=_NOW - 7200)

    assert (
        repo.decrement_counter("u1", "generateCount", "windowStart", 3600, _NOW)
        is False
    )
    assert _counter(repo, "u1", "generateCount") == 1


def test_decrement_on_a_missing_record_is_a_no_op(repo):
    assert (
        repo.decrement_counter("nobody", "generateCount", "windowStart", 3600, _NOW)
        is False
    )
    assert repo.get_user("nobody") is None


def test_decrement_touches_only_the_named_counter(repo):
    _seed(repo, "u1", generateCount=1, refineCount=2, windowStart=_NOW - 10)

    repo.decrement_counter("u1", "refineCount", "windowStart", 3600, _NOW)

    assert _counter(repo, "u1", "generateCount") == 1
    assert _counter(repo, "u1", "refineCount") == 1


def test_decrement_reads_the_window_field_it_is_given(repo):
    """A daily counter is judged against dailyResetAt, not windowStart."""
    _seed(repo, "u1", dailyCount=1, dailyResetAt=_NOW - 10, windowStart=_NOW - 999_999)

    assert (
        repo.decrement_counter("u1", "dailyCount", "dailyResetAt", 86400, _NOW) is True
    )
    assert _counter(repo, "u1", "dailyCount") == 0


def test_decrement_propagates_a_non_conditional_client_error(repo):
    """A throttle or an access denial is not "nothing to refund"."""
    from botocore.exceptions import ClientError

    repo._table = MagicMock()
    repo._table.update_item.side_effect = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException"}}, "UpdateItem"
    )

    with pytest.raises(ClientError):
        repo.decrement_counter("u1", "generateCount", "windowStart", 3600, _NOW)


# --------------------------------------------------------------------------
# _refund_usage
# --------------------------------------------------------------------------


@pytest.fixture
def wired(monkeypatch):
    """lambda_function with the real repository over moto DynamoDB."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "secret")
    monkeypatch.setenv("FREE_GENERATE_LIMIT", "1")
    monkeypatch.setenv("FREE_REFINE_LIMIT", "2")
    monkeypatch.setenv("FREE_WINDOW_SECONDS", "3600")
    monkeypatch.setenv("PAID_DAILY_LIMIT", "3")
    monkeypatch.setenv("ANON_GENERATE_LIMIT", "1")
    import config as cfg

    importlib.reload(cfg)
    import auth.guest_token as gt

    gt.reset_guest_token_service()
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        _make_table(ddb)
        import lambda_function

        importlib.reload(lambda_function)
        from users.repository import UserRepository

        lambda_function._user_repo = UserRepository(_TABLE, dynamodb_resource=ddb)
        # Synchronous dispatch so run_generation -- which owns the all-error
        # refund -- executes in-process. Pinned rather than left to chance:
        # async mode only falls back inline because AWS_LAMBDA_FUNCTION_NAME
        # happens to be unset here.
        monkeypatch.setattr(lambda_function.config, "generate_async", False)
        yield lambda_function
    for v in (
        "GUEST_TOKEN_SECRET",
        "FREE_GENERATE_LIMIT",
        "FREE_REFINE_LIMIT",
        "FREE_WINDOW_SECONDS",
        "PAID_DAILY_LIMIT",
        "ANON_GENERATE_LIMIT",
    ):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("AUTH_ENABLED", "false")
    importlib.reload(cfg)
    gt.reset_guest_token_service()


def _ctx(tier, user_id):
    return TierContext(
        tier=tier,
        user_id=user_id,
        email=None,
        is_authenticated=tier in ("free", "paid"),
        guest_token_id="tok" if tier == "guest" else None,
        issue_guest_cookie=False,
        ip_hash="hash" if tier in ("anon", "guest") else None,
    )


def test_refund_gives_a_free_user_their_generate_back(wired):
    _seed(wired._user_repo, "u1", generateCount=1, refineCount=0, windowStart=_NOW)

    with patch.object(wired.time, "time", return_value=_NOW):
        wired._refund_usage(_ctx("free", "u1"), "generate")

    assert _counter(wired._user_repo, "u1", "generateCount") == 0


def test_refund_gives_a_free_user_their_refine_back(wired):
    _seed(wired._user_repo, "u1", generateCount=0, refineCount=1, windowStart=_NOW)

    with patch.object(wired.time, "time", return_value=_NOW):
        wired._refund_usage(_ctx("free", "u1"), "refine")

    assert _counter(wired._user_repo, "u1", "refineCount") == 0


def test_refund_of_an_outpaint_returns_the_refine_it_consumed(wired):
    """/outpaint is metered on refineCount, so that is what it gives back."""
    _seed(wired._user_repo, "u1", refineCount=1, windowStart=_NOW)

    with patch.object(wired.time, "time", return_value=_NOW):
        wired._refund_usage(_ctx("free", "u1"), "outpaint")

    assert _counter(wired._user_repo, "u1", "refineCount") == 0


def test_refund_gives_a_paid_user_their_daily_refine_back(wired):
    _seed(wired._user_repo, "p1", dailyCount=1, dailyResetAt=_NOW)

    with patch.object(wired.time, "time", return_value=_NOW):
        wired._refund_usage(_ctx("paid", "p1"), "refine")

    assert _counter(wired._user_repo, "p1", "dailyCount") == 0


def test_refund_covers_the_anon_tier_that_open_source_mode_runs_on(wired):
    """AUTH_ENABLED=false is metered, so it needs refunds for the same reason."""
    _seed(wired._user_repo, "anon#hash", generateCount=1, windowStart=_NOW)

    with patch.object(wired.time, "time", return_value=_NOW):
        wired._refund_usage(_ctx("anon", "anon#hash"), "generate")

    assert _counter(wired._user_repo, "anon#hash", "generateCount") == 0


def test_refund_covers_anon_refinement(wired):
    _seed(wired._user_repo, "anon#hash", refineCount=1, windowStart=_NOW)

    with patch.object(wired.time, "time", return_value=_NOW):
        wired._refund_usage(_ctx("anon", "anon#hash"), "refine")

    assert _counter(wired._user_repo, "anon#hash", "refineCount") == 0


def test_refund_is_a_no_op_for_a_guest_on_the_counter_path(wired):
    """A guest identity is a cookie delete away, so a refund is a free retry."""
    _seed(wired._user_repo, "guest#tok", generateCount=1, windowStart=_NOW)

    with patch.object(wired.time, "time", return_value=_NOW):
        wired._refund_usage(_ctx("guest", "guest#tok"), "generate")

    assert _counter(wired._user_repo, "guest#tok", "generateCount") == 1


def test_refund_is_a_no_op_for_a_guest_on_the_credit_path(wired, monkeypatch):
    monkeypatch.setattr(wired.config, "credits_enabled", True)
    _seed(
        wired._user_repo,
        "guest#tok",
        creditsRemaining=0,
        generateCount=1,
        windowStart=_NOW,
    )

    wired._refund_usage(_ctx("guest", "guest#tok"), "generate")

    assert _counter(wired._user_repo, "guest#tok", "creditsRemaining") == 0
    assert _counter(wired._user_repo, "guest#tok", "generateCount") == 1


def test_refund_with_credits_on_grants_credits_and_leaves_counters_alone(
    wired, monkeypatch
):
    monkeypatch.setattr(wired.config, "credits_enabled", True)
    _seed(wired._user_repo, "u1", creditsRemaining=0, generateCount=1, windowStart=_NOW)

    wired._refund_usage(_ctx("free", "u1"), "generate")

    assert _counter(
        wired._user_repo, "u1", "creditsRemaining"
    ) == wired.config.credit_cost("generate")
    assert _counter(wired._user_repo, "u1", "generateCount") == 1


def test_refund_with_credits_off_leaves_the_credit_balance_alone(wired):
    _seed(wired._user_repo, "u1", creditsRemaining=0, generateCount=1, windowStart=_NOW)

    with patch.object(wired.time, "time", return_value=_NOW):
        wired._refund_usage(_ctx("free", "u1"), "generate")

    assert _counter(wired._user_repo, "u1", "creditsRemaining") == 0


def test_refund_of_a_none_tier_is_a_no_op(wired):
    wired._refund_usage(None, "generate")


def test_a_failed_refund_is_logged_and_never_raised(wired, caplog):
    """The caller is already on an error path; a second failure there helps nobody."""
    wired._user_repo = MagicMock()
    wired._user_repo.decrement_counter.side_effect = RuntimeError("dynamodb down")

    with caplog.at_level("ERROR"):
        wired._refund_usage(_ctx("free", "u1"), "generate")

    assert any("refund" in r.getMessage().lower() for r in caplog.records)


# --------------------------------------------------------------------------
# End to end: the user-visible behaviour the finding is about
# --------------------------------------------------------------------------


def _generate_event(claims):
    return {
        "rawPath": "/generate",
        "requestContext": {
            "http": {"method": "POST", "sourceIp": "1.2.3.4"},
            "authorizer": {"jwt": {"claims": claims}},
        },
        "headers": {},
        "body": json.dumps({"prompt": "a cat"}),
    }


def _all_models_fail(wired):
    """Patch the provider seam so every dispatched model returns an error."""
    fake_model = MagicMock(provider="google_gemini")
    fake_model.name = "gemini"
    return (
        patch.object(wired, "get_enabled_models", return_value=[fake_model]),
        patch.object(wired, "session_manager"),
        patch.object(wired, "image_storage"),
        patch.object(wired, "context_manager"),
        patch.object(wired, "get_model_config_dict", return_value={"id": "x"}),
        patch.object(
            wired,
            "get_handler",
            return_value=lambda c, p, params: {
                "status": "error",
                "error": "provider down",
            },
        ),
        fake_model,
    )


def test_a_free_user_whose_generation_produced_nothing_can_generate_again(wired):
    """The finding, at the level the user experiences it.

    FREE_GENERATE_LIMIT=1. The first generation fails on every model, so the
    hour's whole allowance bought nothing. With CREDITS_ENABLED false -- the
    shipped default -- the refund machinery used to return immediately and the
    second call was refused with a 429.
    """
    claims = {"sub": "free-refund-e2e", "email": "u@x.com"}
    p_models, p_sm, p_img, p_cm, p_cfg, p_gh, fake_model = _all_models_fail(wired)

    with p_models, p_sm as sm, p_img as img, p_cm, p_cfg, p_gh:
        sm.create_session.return_value = "sess"
        sm.add_iteration.return_value = 0
        img.upload_image.return_value = "k"
        img.get_cloudfront_url.return_value = "https://cdn/k"

        first = wired.lambda_handler(_generate_event(claims), None)
        used_after_first = _counter(
            wired._user_repo, "free-refund-e2e", "generateCount"
        )
        second = wired.lambda_handler(_generate_event(claims), None)

    assert first["statusCode"] == 200
    assert used_after_first == 0, "the failed generation should have been refunded"
    assert second["statusCode"] != 429, json.loads(second["body"])


def test_a_free_user_whose_generation_succeeded_keeps_paying_for_it(wired):
    """The refund must not fire on success, or the limit bounds nothing."""
    claims = {"sub": "free-success-e2e", "email": "u@x.com"}
    fake_model = MagicMock(provider="google_gemini")
    fake_model.name = "gemini"

    with (
        patch.object(wired, "get_enabled_models", return_value=[fake_model]),
        patch.object(wired, "session_manager") as sm,
        patch.object(wired, "image_storage") as img,
        patch.object(wired, "context_manager"),
        patch.object(wired, "get_model_config_dict", return_value={"id": "x"}),
        patch.object(
            wired,
            "get_handler",
            return_value=lambda c, p, params: {"status": "success", "image": "b"},
        ),
    ):
        sm.create_session.return_value = "sess"
        sm.add_iteration.return_value = 0
        img.upload_image.return_value = "k"
        img.get_cloudfront_url.return_value = "https://cdn/k"

        first = wired.lambda_handler(_generate_event(claims), None)
        used_after_first = _counter(
            wired._user_repo, "free-success-e2e", "generateCount"
        )
        second = wired.lambda_handler(_generate_event(claims), None)

    assert first["statusCode"] == 200
    assert used_after_first == 1
    assert second["statusCode"] == 429
