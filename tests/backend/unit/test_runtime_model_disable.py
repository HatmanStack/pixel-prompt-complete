"""An admin kill switch has to reach every path that spends money on a model.

What these tests prove: ``config#model#<name>.disabled`` is consulted by
``/generate``, ``/iterate`` and ``/outpaint`` alike, that a disabled model
reaches no provider handler and consumes no per-model cap slot, that the
refusal refunds the quota it consumed, and that an unreachable config store
lets refinement through rather than taking the service down with it.

The kill-switch assertions are deliberately about the call that does NOT
happen. A test that only checked the status code would pass against an
implementation that refuses the caller after dispatching to the provider,
which is the exact failure the switch exists to prevent.

What they cannot prove: that the admin endpoint's write and this read race
correctly. They are separate DynamoDB items under a single-writer control
plane, and eventual visibility of a disable is acceptable by design.
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

_TABLE = "pixel-prompt-users"
_CLAIMS = {"sub": "free-killswitch", "email": "u@x.com"}


@pytest.fixture
def wired(monkeypatch):
    """lambda_function with the real repository over moto DynamoDB."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("GUEST_TOKEN_SECRET", "secret")
    monkeypatch.setenv("FREE_GENERATE_LIMIT", "1")
    monkeypatch.setenv("FREE_REFINE_LIMIT", "1")
    monkeypatch.setenv("FREE_WINDOW_SECONDS", "3600")
    # Without a key gemini is disabled at CONFIG level, which is a different
    # refusal (400 from get_model) than the runtime kill switch under test.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    import config as cfg

    importlib.reload(cfg)
    import auth.guest_token as gt

    gt.reset_guest_token_service()
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=_TABLE,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        import lambda_function

        importlib.reload(lambda_function)
        from users.repository import UserRepository

        lambda_function._user_repo = UserRepository(_TABLE, dynamodb_resource=ddb)
        monkeypatch.setattr(lambda_function.config, "generate_async", False)
        yield lambda_function
    for v in (
        "GUEST_TOKEN_SECRET",
        "FREE_GENERATE_LIMIT",
        "FREE_REFINE_LIMIT",
        "FREE_WINDOW_SECONDS",
        "GEMINI_API_KEY",
    ):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("AUTH_ENABLED", "false")
    importlib.reload(cfg)
    gt.reset_guest_token_service()


def _event(path, body):
    return {
        "rawPath": path,
        "requestContext": {
            "http": {"method": "POST", "sourceIp": "1.2.3.4"},
            "authorizer": {"jwt": {"claims": _CLAIMS}},
        },
        "headers": {},
        "body": json.dumps(body),
    }


def _iterate_event(model="gemini"):
    return _event(
        "/iterate", {"sessionId": "sess-1", "model": model, "prompt": "bluer"}
    )


def _outpaint_event(model="gemini"):
    return _event(
        "/outpaint", {"sessionId": "sess-1", "model": model, "preset": "16:9"}
    )


def _refinement_seams(wired):
    """Patch everything downstream of the kill-switch check.

    ``get_iterate_handler`` / ``get_outpaint_handler`` and
    ``consume_model_slot`` are the two things a working switch must not reach.
    """
    session = {
        "sessionId": "sess-1",
        "visibility": "public",
        "models": {
            "gemini": {
                "iterationCount": 1,
                "iterations": [
                    {"index": 0, "status": "completed", "imageKey": "k.png"}
                ],
            },
            "nova": {
                "iterationCount": 1,
                "iterations": [
                    {"index": 0, "status": "completed", "imageKey": "k.png"}
                ],
            },
        },
    }
    sm = patch.object(wired, "session_manager")
    img = patch.object(wired, "image_storage")
    cm = patch.object(wired, "context_manager")
    gmc = patch.object(wired, "get_model_config_dict", return_value={"id": "x"})
    gih = patch.object(wired, "get_iterate_handler")
    goh = patch.object(wired, "get_outpaint_handler")
    counters = patch.object(wired, "_model_counter_service")
    return session, sm, img, cm, gmc, gih, goh, counters


def _counter(wired, user_id, name):
    item = wired._user_repo.get_user(user_id) or {}
    return int(item.get(name, 0) or 0)


# --------------------------------------------------------------------------
# /iterate and /outpaint
# --------------------------------------------------------------------------


def test_a_disabled_model_refuses_iterate_with_503_and_dispatches_nothing(wired):
    wired._user_repo.set_model_runtime_config("gemini", True)
    session, sm, img, cm, gmc, gih, goh, counters = _refinement_seams(wired)

    with sm as m_sm, img as m_img, cm, gmc, gih as m_gih, goh, counters as m_counters:
        m_sm.get_session.return_value = session
        m_sm.add_iteration.return_value = 1
        m_img.get_image_bytes.return_value = b"\x89PNG"
        m_counters.consume_model_slot.return_value = True

        resp = wired.lambda_handler(_iterate_event(), None)

        assert resp["statusCode"] == 503
        assert json.loads(resp["body"])["error"] == "MODEL_DISABLED"
        assert m_gih.call_count == 0, (
            "a disabled model still reached a provider handler"
        )
        assert m_counters.consume_model_slot.call_count == 0
        assert m_sm.add_iteration.call_count == 0


def test_a_disabled_model_refuses_outpaint_with_503_and_dispatches_nothing(wired):
    wired._user_repo.set_model_runtime_config("gemini", True)
    session, sm, img, cm, gmc, gih, goh, counters = _refinement_seams(wired)

    with sm as m_sm, img as m_img, cm, gmc, gih, goh as m_goh, counters as m_counters:
        m_sm.get_session.return_value = session
        m_sm.add_iteration.return_value = 1
        m_img.get_image_bytes.return_value = b"\x89PNG"
        m_counters.consume_model_slot.return_value = True

        resp = wired.lambda_handler(_outpaint_event(), None)

        assert resp["statusCode"] == 503
        assert json.loads(resp["body"])["error"] == "MODEL_DISABLED"
        assert m_goh.call_count == 0, (
            "a disabled model still reached a provider handler"
        )
        assert m_counters.consume_model_slot.call_count == 0


def test_the_refusal_gives_the_caller_their_refine_quota_back(wired):
    """FREE_REFINE_LIMIT=1, so without the refund one refusal costs the hour."""
    wired._user_repo.set_model_runtime_config("gemini", True)
    session, sm, img, cm, gmc, gih, goh, counters = _refinement_seams(wired)

    with sm as m_sm, img as m_img, cm, gmc, gih, goh, counters as m_counters:
        m_sm.get_session.return_value = session
        m_sm.add_iteration.return_value = 1
        m_img.get_image_bytes.return_value = b"\x89PNG"
        m_counters.consume_model_slot.return_value = True

        first = wired.lambda_handler(_iterate_event(), None)
        used = _counter(wired, _CLAIMS["sub"], "refineCount")

    assert first["statusCode"] == 503
    assert used == 0, "a request refused before any provider work still cost quota"


def test_an_enabled_model_is_unaffected(wired):
    wired._user_repo.set_model_runtime_config("gemini", True)
    session, sm, img, cm, gmc, gih, goh, counters = _refinement_seams(wired)

    with (
        sm as m_sm,
        img as m_img,
        cm as m_cm,
        gmc,
        gih as m_gih,
        goh,
        counters as m_counters,
    ):
        m_sm.get_session.return_value = session
        m_sm.add_iteration.return_value = 1
        m_img.get_image_bytes.return_value = b"\x89PNG"
        m_img.upload_image.return_value = "k2.png"
        m_img.get_cloudfront_url.return_value = "https://cdn/k2.png"
        m_cm.get_context_for_iteration.return_value = []
        m_counters.consume_model_slot.return_value = True
        m_gih.return_value = lambda c, s, p, ctx: {"status": "success", "image": "b"}

        resp = wired.lambda_handler(_iterate_event(model="nova"), None)

    assert resp["statusCode"] == 200, resp["body"]


def test_a_model_disabled_then_re_enabled_serves_refinement_again(wired):
    """The switch is a switch, not a one-way door."""
    wired._user_repo.set_model_runtime_config("gemini", True)
    wired._user_repo.set_model_runtime_config("gemini", False)
    session, sm, img, cm, gmc, gih, goh, counters = _refinement_seams(wired)

    with (
        sm as m_sm,
        img as m_img,
        cm as m_cm,
        gmc,
        gih as m_gih,
        goh,
        counters as m_counters,
    ):
        m_sm.get_session.return_value = session
        m_sm.add_iteration.return_value = 1
        m_img.get_image_bytes.return_value = b"\x89PNG"
        m_img.upload_image.return_value = "k2.png"
        m_img.get_cloudfront_url.return_value = "https://cdn/k2.png"
        m_cm.get_context_for_iteration.return_value = []
        m_counters.consume_model_slot.return_value = True
        m_gih.return_value = lambda c, s, p, ctx: {"status": "success", "image": "b"}

        resp = wired.lambda_handler(_iterate_event(), None)

    assert resp["statusCode"] == 200, resp["body"]


def test_an_unreachable_config_store_lets_refinement_through(wired, caplog):
    """Fails OPEN, like every other guard that reads this table.

    An unreachable store is not evidence a model is disabled, and refusing all
    refinement because DynamoDB hiccuped would be a self-inflicted outage.
    """
    session, sm, img, cm, gmc, gih, goh, counters = _refinement_seams(wired)
    broken = MagicMock(wraps=wired._user_repo)
    broken.get_model_runtime_config.side_effect = RuntimeError("dynamodb down")
    wired._user_repo = broken

    with (
        sm as m_sm,
        img as m_img,
        cm as m_cm,
        gmc,
        gih as m_gih,
        goh,
        counters as m_counters,
    ):
        m_sm.get_session.return_value = session
        m_sm.add_iteration.return_value = 1
        m_img.get_image_bytes.return_value = b"\x89PNG"
        m_img.upload_image.return_value = "k2.png"
        m_img.get_cloudfront_url.return_value = "https://cdn/k2.png"
        m_cm.get_context_for_iteration.return_value = []
        m_counters.consume_model_slot.return_value = True
        m_gih.return_value = lambda c, s, p, ctx: {"status": "success", "image": "b"}

        with caplog.at_level("ERROR"):
            resp = wired.lambda_handler(_iterate_event(), None)

    assert resp["statusCode"] == 200, resp["body"]
    assert any(
        "gemini" in r.getMessage() and "runtime" in r.getMessage().lower()
        for r in caplog.records
    ), "the fail-open path must be alarmable"


# --------------------------------------------------------------------------
# /generate uses the same helper
# --------------------------------------------------------------------------


def test_generate_skips_a_disabled_model_through_the_same_helper(wired):
    wired._user_repo.set_model_runtime_config("gemini", True)
    gemini = MagicMock(provider="google_gemini")
    gemini.name = "gemini"
    nova = MagicMock(provider="bedrock_nova")
    nova.name = "nova"

    with (
        patch.object(wired, "get_enabled_models", return_value=[gemini, nova]),
        patch.object(wired, "session_manager") as sm,
        patch.object(wired, "image_storage") as img,
        patch.object(wired, "context_manager"),
        patch.object(wired, "get_model_config_dict", return_value={"id": "x"}),
        patch.object(wired, "get_handler") as gh,
        patch.object(wired, "_model_counter_service") as counters,
    ):
        sm.create_session.return_value = "sess"
        sm.add_iteration.return_value = 0
        img.upload_image.return_value = "k"
        img.get_cloudfront_url.return_value = "https://cdn/k"
        counters.consume_model_slot.return_value = True
        gh.return_value = lambda c, p, params: {"status": "success", "image": "b"}

        resp = wired.lambda_handler(_event("/generate", {"prompt": "a cat"}), None)

    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200, body
    assert body["models"]["gemini"] == {"status": "skipped", "reason": "admin_disabled"}
    assert "gemini" not in [
        c.args[0] for c in counters.consume_model_slot.call_args_list
    ]


def test_the_runtime_config_read_lives_in_exactly_one_place(wired):
    """A fourth dispatch path must not be able to diverge silently.

    Read as source text rather than behaviour on purpose: the finding was that
    two of three paths forgot to ask, and the guard against a fourth is that
    there is only one caller to copy.
    """
    import inspect

    source = inspect.getsource(wired)
    assert source.count("get_model_runtime_config(") == 1


# --------------------------------------------------------------------------
# Per-model cap ordering
# --------------------------------------------------------------------------


def test_a_capped_model_refuses_refinement_without_writing_an_iteration(wired):
    """The cap 429 must be ordered like the kill switch: before add_iteration.

    This branch returns without ever calling `_handle_failed_result`, so a row
    written first stays `in_progress` forever. `_compute_model_status` then
    reports the model in progress and `_compute_session_status` the session,
    so the client polls a spinner that never resolves -- while one of the
    model's MAX_ITERATIONS slots stays spent on work that never ran.
    """
    session, sm, img, cm, gmc, gih, goh, counters = _refinement_seams(wired)

    with sm as m_sm, img as m_img, cm, gmc, gih as m_gih, goh, counters as m_counters:
        m_sm.get_session.return_value = session
        m_sm.add_iteration.return_value = 1
        m_img.get_image_bytes.return_value = b"\x89PNG"
        m_counters.consume_model_slot.return_value = False

        resp = wired.lambda_handler(_iterate_event(), None)

        assert resp["statusCode"] == 429
        assert json.loads(resp["body"])["error"] == "MODEL_COST_CEILING"
        assert m_gih.call_count == 0, "a capped model still reached a provider"
        assert m_sm.add_iteration.call_count == 0, (
            "an iteration row was written for a refinement that never ran, "
            "and nothing will ever move it out of in_progress"
        )


def test_a_capped_model_refuses_outpaint_without_writing_an_iteration(wired):
    session, sm, img, cm, gmc, gih, goh, counters = _refinement_seams(wired)

    with sm as m_sm, img as m_img, cm, gmc, gih, goh as m_goh, counters as m_counters:
        m_sm.get_session.return_value = session
        m_sm.add_iteration.return_value = 1
        m_img.get_image_bytes.return_value = b"\x89PNG"
        m_counters.consume_model_slot.return_value = False

        resp = wired.lambda_handler(_outpaint_event(), None)

        assert resp["statusCode"] == 429
        assert m_goh.call_count == 0
        assert m_sm.add_iteration.call_count == 0


def test_an_uncapped_model_still_writes_its_iteration(wired):
    """The guard above must not stop a normal refinement recording its work."""
    session, sm, img, cm, gmc, gih, goh, counters = _refinement_seams(wired)

    with sm as m_sm, img as m_img, cm, gmc, gih as m_gih, goh, counters as m_counters:
        m_sm.get_session.return_value = session
        m_sm.add_iteration.return_value = 1
        m_img.get_image_bytes.return_value = b"\x89PNG"
        m_counters.consume_model_slot.return_value = True
        m_gih.return_value = lambda *a, **k: {"status": "success", "image": "aW1n"}

        wired.lambda_handler(_iterate_event(), None)

        assert m_sm.add_iteration.call_count == 1
