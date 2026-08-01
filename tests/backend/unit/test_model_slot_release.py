"""A shared model slot must not stay spent on work that never ran.

``_handle_refinement`` consumes the per-model daily slot *before* calling
``add_iteration``, and deliberately so: the reverse order strands an
``in_progress`` iteration row when the cap refuses, and the client polls a
spinner that never resolves. But the ordering left a gap. ``add_iteration``
re-reads the session under an ETag and re-checks the iteration limit, so
concurrent refinements at the last iteration can all pass the handler's
earlier read, one wins, and the losers raise — having already taken a slot
off a cap that is shared by every user of the service. Nothing gave it back.

What these tests prove: a slot taken is a slot returned whenever the request
fails before reaching a provider, and a slot is NOT returned once a provider
has been dispatched, because at that point the image has been generated and
billed whatever the outcome.

What they cannot prove: that a real concurrent race interleaves correctly.
moto is not thread-safe, so the losing writer is modelled by making
``add_iteration`` raise the same error a lost ETag race produces.
"""

from __future__ import annotations

import importlib
import json
import os
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

_TABLE = "pixel-prompt-users"
_CLAIMS = {"sub": "free-slot-user", "email": "u@x.com"}


@pytest.fixture
def users_table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=_TABLE,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield _TABLE, ddb


def _repo(users_table):
    from users.repository import UserRepository

    return UserRepository(users_table[0], dynamodb_resource=users_table[1])


# --------------------------------------------------------------------------
# The counter primitive
# --------------------------------------------------------------------------


def test_release_returns_a_consumed_slot(users_table):
    from ops.model_counters import ModelCounterService

    svc = ModelCounterService(_repo(users_table))
    now = 1_000_000

    svc.consume_model_slot("gemini", now)
    svc.consume_model_slot("gemini", now)
    assert svc.get_model_counts(now)["gemini"]["dailyCount"] == 2

    assert svc.release_model_slot("gemini", now) is True
    assert svc.get_model_counts(now)["gemini"]["dailyCount"] == 1


def test_release_frees_capacity_at_the_cap(users_table):
    """The point of the release: the freed slot is usable again."""
    from ops.model_counters import ModelCounterService

    svc = ModelCounterService(_repo(users_table))
    now = 1_000_000
    caps = {"gemini": 2, "nova": 500, "openai": 500, "firefly": 500}

    with patch("config.MODEL_DAILY_CAPS", caps):
        assert svc.consume_model_slot("gemini", now) is True
        assert svc.consume_model_slot("gemini", now) is True
        assert svc.consume_model_slot("gemini", now) is False

        assert svc.release_model_slot("gemini", now) is True
        assert svc.consume_model_slot("gemini", now) is True


def test_release_cannot_drive_the_counter_negative(users_table):
    """A release with nothing to give back is a no-op, not extra allowance."""
    from ops.model_counters import ModelCounterService

    svc = ModelCounterService(_repo(users_table))
    now = 1_000_000

    assert svc.release_model_slot("gemini", now) is False
    assert svc.get_model_counts(now)["gemini"]["dailyCount"] == 0


def test_release_does_not_credit_an_expired_window(users_table):
    """A window that has already rolled handed out a fresh allowance.

    Crediting it for a slot spent in the previous one is a free extra
    generation stacked on top of the reset.

    The guard is ``decrement_counter``'s, and it is worth being exact about
    what it does: it refuses when the *record's* window is stale relative to
    the clock the caller passes. It does not detect a caller passing a stale
    clock while the record has rolled forward -- and does not need to, because
    _release_model_slot passes ``time.time()`` and runs in the same request
    that consumed the slot. The residual is a window rolling between the
    consume and the release, milliseconds apart, costing one slot off a daily
    cap. That is the same bound _refund_usage accepts for the per-user
    counter, and it is deliberately not tightened here alone.
    """
    from ops.model_counters import ModelCounterService

    svc = ModelCounterService(_repo(users_table))
    now = 1_000_000

    svc.consume_model_slot("gemini", now)
    assert svc.release_model_slot("gemini", now + 86_400 + 1) is False
    assert svc.get_model_counts(now)["gemini"]["dailyCount"] == 1


# --------------------------------------------------------------------------
# The refinement path
# --------------------------------------------------------------------------


@pytest.fixture
def wired(monkeypatch):
    """lambda_function with a real counter service over moto DynamoDB."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "secret")
    monkeypatch.setenv("FREE_REFINE_LIMIT", "10")
    monkeypatch.setenv("FREE_WINDOW_SECONDS", "3600")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    import config as cfg

    importlib.reload(cfg)
    import auth.guest_token as gt

    gt.reset_guest_token_service()
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=_TABLE,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        import lambda_function

        importlib.reload(lambda_function)
        from ops.model_counters import ModelCounterService
        from users.repository import UserRepository

        repo = UserRepository(_TABLE, dynamodb_resource=ddb)
        lambda_function._user_repo = repo
        lambda_function._model_counter_service = ModelCounterService(repo)
        monkeypatch.setattr(lambda_function.config, "generate_async", False)
        yield lambda_function
    for v in ("GUEST_TOKEN_SECRET", "FREE_REFINE_LIMIT", "FREE_WINDOW_SECONDS", "GEMINI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("AUTH_ENABLED", "false")
    importlib.reload(cfg)
    gt.reset_guest_token_service()


def _iterate_event():
    return {
        "rawPath": "/iterate",
        "requestContext": {
            "http": {"method": "POST", "sourceIp": "1.2.3.4"},
            "authorizer": {"jwt": {"claims": _CLAIMS}},
        },
        "headers": {},
        "body": json.dumps({"sessionId": "sess-1", "model": "gemini", "prompt": "bluer"}),
    }


_SESSION = {
    "sessionId": "sess-1",
    "visibility": "public",
    "models": {
        "gemini": {
            "iterationCount": 1,
            "iterations": [{"index": 0, "status": "completed", "imageKey": "k.png"}],
        }
    },
}


def _slot_count(wired):
    return wired._model_counter_service.get_model_counts(0)["gemini"]["dailyCount"]


def test_a_lost_iteration_race_returns_the_model_slot(wired):
    """The finding: the losing writer must not keep the slot it took."""
    with (
        patch.object(wired, "session_manager") as m_sm,
        patch.object(wired, "image_storage") as m_img,
        patch.object(wired, "context_manager"),
        patch.object(wired, "get_model_config_dict", return_value={"id": "x"}),
        patch.object(wired, "get_iterate_handler") as m_gih,
    ):
        m_sm.get_session.return_value = _SESSION
        m_img.get_image_bytes.return_value = b"\x89PNG"
        # What a losing ETag writer sees once the winner takes the last slot.
        m_sm.add_iteration.side_effect = ValueError(
            "Maximum iterations (7) reached for model gemini"
        )

        resp = wired.lambda_handler(_iterate_event(), None)

        assert resp["statusCode"] == 500
        assert m_gih.call_count == 0, "no provider should have been reached"
        assert _slot_count(wired) == 0, "the model slot was consumed by work that never ran"


def test_a_failure_between_the_slot_and_the_provider_returns_it(wired):
    """Anything before dispatch, not just add_iteration."""
    with (
        patch.object(wired, "session_manager") as m_sm,
        patch.object(wired, "image_storage") as m_img,
        patch.object(wired, "context_manager") as m_cm,
        patch.object(wired, "get_model_config_dict", return_value={"id": "x"}),
        patch.object(wired, "get_iterate_handler"),
    ):
        m_sm.get_session.return_value = _SESSION
        m_sm.add_iteration.return_value = 1
        m_img.get_image_bytes.return_value = b"\x89PNG"
        # Building the handler arguments reads the rolling context from S3.
        m_cm.get_context_for_iteration.side_effect = RuntimeError("s3 unavailable")

        resp = wired.lambda_handler(_iterate_event(), None)

        assert resp["statusCode"] == 500
        assert _slot_count(wired) == 0


def test_a_dispatched_provider_keeps_the_slot(wired):
    """Once the provider ran, the image was generated and billed.

    Returning the slot here would let a caller whose provider call throws
    after the request left us spend the cap twice for one generation.
    """
    with (
        patch.object(wired, "session_manager") as m_sm,
        patch.object(wired, "image_storage") as m_img,
        patch.object(wired, "context_manager"),
        patch.object(wired, "get_model_config_dict", return_value={"id": "x"}),
        patch.object(wired, "get_iterate_handler") as m_gih,
    ):
        m_sm.get_session.return_value = _SESSION
        m_sm.add_iteration.return_value = 1
        m_img.get_image_bytes.return_value = b"\x89PNG"
        m_gih.return_value.side_effect = RuntimeError("provider exploded mid-call")

        resp = wired.lambda_handler(_iterate_event(), None)

        assert resp["statusCode"] == 500
        assert _slot_count(wired) == 1


def test_a_provider_error_result_keeps_the_slot(wired):
    """A handler that reports failure still ran the model."""
    with (
        patch.object(wired, "session_manager") as m_sm,
        patch.object(wired, "image_storage") as m_img,
        patch.object(wired, "context_manager"),
        patch.object(wired, "get_model_config_dict", return_value={"id": "x"}),
        patch.object(wired, "get_iterate_handler") as m_gih,
    ):
        m_sm.get_session.return_value = _SESSION
        m_sm.add_iteration.return_value = 1
        m_img.get_image_bytes.return_value = b"\x89PNG"
        m_gih.return_value.return_value = {"status": "error", "error": "content filtered"}

        resp = wired.lambda_handler(_iterate_event(), None)

        assert resp["statusCode"] == 500
        assert _slot_count(wired) == 1


def test_a_successful_refinement_keeps_the_slot(wired):
    with (
        patch.object(wired, "session_manager") as m_sm,
        patch.object(wired, "image_storage") as m_img,
        patch.object(wired, "context_manager"),
        patch.object(wired, "get_model_config_dict", return_value={"id": "x"}),
        patch.object(wired, "get_iterate_handler") as m_gih,
    ):
        m_sm.get_session.return_value = _SESSION
        m_sm.add_iteration.return_value = 1
        m_img.get_image_bytes.return_value = b"\x89PNG"
        m_img.upload_image.return_value = "sessions/2026-01-01-00-00-00-abcd1234/gemini.png"
        m_img.is_private_key.return_value = False
        m_img.validate_gallery_id.return_value = True
        m_img.get_cloudfront_url.return_value = "https://cdn.example.com/x.png"
        m_gih.return_value.return_value = {"status": "success", "image": "aGk="}

        resp = wired.lambda_handler(_iterate_event(), None)

        assert resp["statusCode"] == 200
        assert _slot_count(wired) == 1


def test_a_store_failure_taking_the_slot_releases_nothing(wired):
    """The cap check fails open; nothing was taken, so nothing is owed back.

    Releasing on the fail-open path would decrement a counter this request
    never incremented, stealing capacity from whoever did.
    """
    with (
        patch.object(wired, "session_manager") as m_sm,
        patch.object(wired, "image_storage") as m_img,
        patch.object(wired, "context_manager"),
        patch.object(wired, "get_model_config_dict", return_value={"id": "x"}),
        patch.object(wired, "get_iterate_handler"),
        patch.object(
            wired._model_counter_service,
            "consume_model_slot",
            side_effect=RuntimeError("dynamo unavailable"),
        ),
        patch.object(wired._model_counter_service, "release_model_slot") as m_release,
    ):
        m_sm.get_session.return_value = _SESSION
        m_img.get_image_bytes.return_value = b"\x89PNG"
        m_sm.add_iteration.side_effect = ValueError("Maximum iterations reached")

        wired.lambda_handler(_iterate_event(), None)

        assert m_release.call_count == 0


# --------------------------------------------------------------------------
# /generate reserves a slot per model before the session exists
# --------------------------------------------------------------------------


def _generate_event():
    return {
        "rawPath": "/generate",
        "requestContext": {
            "http": {"method": "POST", "sourceIp": "1.2.3.4"},
            "authorizer": {"jwt": {"claims": _CLAIMS}},
        },
        "headers": {},
        "body": json.dumps({"prompt": "a cat", "ageAffirmed": True}),
    }


def _all_slot_counts(wired):
    counts = wired._model_counter_service.get_model_counts(0)
    return {name: counts[name]["dailyCount"] for name in counts}


@pytest.fixture
def wired_generate(wired, monkeypatch):
    """`wired`, with every model enabled and the async dispatch path on."""
    monkeypatch.setattr(wired.config, "generate_async", True)
    monkeypatch.setattr(wired.config, "age_gate_enabled", False)
    return wired


def test_a_failed_async_dispatch_returns_every_reserved_slot(wired_generate):
    """The finding: the 503 refunded the user but kept the shared slots.

    A missing lambda:InvokeFunction grant is the case this branch exists for,
    and it fails every /generate — so leaking here drives all four models to
    their daily cap without a single image being generated.
    """
    wired = wired_generate
    with (
        patch.object(wired, "_dispatch_generation_async", return_value=False),
        patch.object(wired, "session_manager") as m_sm,
    ):
        m_sm.create_session.return_value = "sess-x"

        resp = wired.lambda_handler(_generate_event(), None)

        assert resp["statusCode"] == 503
        assert json.loads(resp["body"])["error"] == "GENERATION_DISPATCH_FAILED"
        assert _all_slot_counts(wired) == dict.fromkeys(
            ("gemini", "nova", "openai", "firefly"), 0
        ), "a dispatch that reached no provider kept its model slots"


def test_a_failure_before_dispatch_returns_every_reserved_slot(wired_generate):
    """create_session raising on an S3 blip is the same shape."""
    wired = wired_generate
    with patch.object(wired, "session_manager") as m_sm:
        m_sm.create_session.side_effect = RuntimeError("s3 unavailable")

        resp = wired.lambda_handler(_generate_event(), None)

        assert resp["statusCode"] == 500
        assert _all_slot_counts(wired) == dict.fromkeys(("gemini", "nova", "openai", "firefly"), 0)


def test_a_dispatched_generation_keeps_its_slots(wired_generate):
    """The reservation bought what it exists to meter.

    Asserted against the models the response says were dispatched rather than
    against all four: which models are config-enabled depends on which API
    keys the fixture sets, and a test that hard-codes four would pass or fail
    on that instead of on the slot accounting.
    """
    wired = wired_generate
    with (
        patch.object(wired, "_dispatch_generation_async", return_value=True),
        patch.object(wired, "session_manager") as m_sm,
    ):
        m_sm.create_session.return_value = "sess-ok"

        resp = wired.lambda_handler(_generate_event(), None)

        assert resp["statusCode"] == 202
        dispatched = {
            name
            for name, info in json.loads(resp["body"])["models"].items()
            if info.get("status") == "pending"
        }
        assert dispatched, "nothing was dispatched, so this proves nothing"

        counts = _all_slot_counts(wired)
        for name in counts:
            expected = 1 if name in dispatched else 0
            assert counts[name] == expected, f"{name}: {counts[name]} != {expected}"
