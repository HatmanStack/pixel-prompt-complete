"""The session lock's conflict and exhaustion paths.

What these tests prove: ``SessionManager``'s three mutators retry a
``PreconditionFailed`` from the conditional write, give up after exactly
``MAX_RETRIES`` attempts with a ``ConcurrencyError`` naming the session,
re-read the session on every attempt, condition each write on the ETag that
same read returned, and never issue a second ``head_object`` to fetch one.

What they cannot prove: that S3's conditional write is correct under real
concurrency. They drive a stubbed client from a single thread. That is a
deliberate choice, not a shortcut -- ``moto`` is not thread-safe, so a threaded
test against it fails as readily because of moto's own shared state as because
of the code, which makes a green run worth nothing and a red run
uninterpretable. The closest this repository gets to real conditional writes is
``tests/backend/e2e/`` against MiniStack, and that is not a concurrency test
either. Same convention as ``tests/backend/unit/test_credit_ledger.py``.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from jobs.manager import MAX_RETRIES, ConcurrencyError, SessionManager

_READ_ETAG = '"etag-from-get-object"'
_HEAD_ETAG = '"etag-from-head-object"'


def _precondition_failed() -> ClientError:
    return ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")


def _session_doc(session_id="sess-1", iteration_count=0, iterations=None):
    return {
        "sessionId": session_id,
        "status": "pending",
        "version": 1,
        "prompt": "a cat",
        "createdAt": "2026-01-01T00:00:00+00:00",
        "updatedAt": "2026-01-01T00:00:00+00:00",
        "ownerId": None,
        "visibility": "public",
        "models": {
            "gemini": {
                "enabled": True,
                "status": "pending",
                "iterationCount": iteration_count,
                "iterations": iterations if iterations is not None else [],
            }
        },
    }


def _stub_client(doc, put_failures=0, read_etags=None):
    """An S3 client whose conditional write fails ``put_failures`` times.

    ``get_object`` and ``head_object`` return DIFFERENT ETags so a write
    conditioned on the wrong one is detectable rather than coincidentally
    correct.
    """
    client = MagicMock()
    etags = read_etags or []
    calls = {"n": 0}

    def _get_object(**_kwargs):
        i = calls["n"]
        calls["n"] += 1
        etag = etags[i] if i < len(etags) else _READ_ETAG
        body = MagicMock()
        body.read.return_value = json.dumps(doc).encode("utf-8")
        return {"Body": body, "ETag": etag}

    client.get_object.side_effect = _get_object
    client.head_object.return_value = {"ETag": _HEAD_ETAG}

    remaining = {"n": put_failures}

    def _put_object(**_kwargs):
        if remaining["n"] > 0:
            remaining["n"] -= 1
            raise _precondition_failed()
        return {}

    client.put_object.side_effect = _put_object
    return client


@pytest.fixture(autouse=True)
def _no_real_sleeping():
    """The backoff is real; waiting for it in a unit test is not useful."""
    with patch("jobs.manager.time.sleep") as sleep:
        yield sleep


# --------------------------------------------------------------------------
# Retry and exhaustion
# --------------------------------------------------------------------------


def test_add_iteration_succeeds_after_the_conflict_clears():
    client = _stub_client(_session_doc(), put_failures=2)
    mgr = SessionManager(client, "bucket")

    index = mgr.add_iteration("sess-1", "gemini", "bluer")

    assert index == 0
    assert client.put_object.call_count == 3
    assert client.get_object.call_count == 3, "each attempt must re-read the session"


def test_add_iteration_raises_concurrency_error_after_exactly_max_retries():
    client = _stub_client(_session_doc(), put_failures=999)
    mgr = SessionManager(client, "bucket")

    with pytest.raises(ConcurrencyError) as excinfo:
        mgr.add_iteration("sess-1", "gemini", "bluer")

    assert client.put_object.call_count == MAX_RETRIES
    assert "sess-1" in str(excinfo.value)


def test_complete_iteration_raises_concurrency_error_after_exactly_max_retries():
    """The one the audit singles out: it runs after the image is billed for."""
    doc = _session_doc(
        iteration_count=1, iterations=[{"index": 0, "status": "in_progress"}]
    )
    client = _stub_client(doc, put_failures=999)
    mgr = SessionManager(client, "bucket")

    with pytest.raises(ConcurrencyError) as excinfo:
        mgr.complete_iteration("sess-1", "gemini", 0, "k.png")

    assert client.put_object.call_count == MAX_RETRIES
    assert "sess-1" in str(excinfo.value)


def test_fail_iteration_raises_concurrency_error_after_exactly_max_retries():
    doc = _session_doc(
        iteration_count=1, iterations=[{"index": 0, "status": "in_progress"}]
    )
    client = _stub_client(doc, put_failures=999)
    mgr = SessionManager(client, "bucket")

    with pytest.raises(ConcurrencyError) as excinfo:
        mgr.fail_iteration("sess-1", "gemini", 0, "provider down")

    assert client.put_object.call_count == MAX_RETRIES
    assert "sess-1" in str(excinfo.value)


def test_complete_iteration_succeeds_after_the_conflict_clears():
    doc = _session_doc(
        iteration_count=1, iterations=[{"index": 0, "status": "in_progress"}]
    )
    client = _stub_client(doc, put_failures=3)
    mgr = SessionManager(client, "bucket")

    mgr.complete_iteration("sess-1", "gemini", 0, "k.png")

    assert client.put_object.call_count == 4
    assert client.get_object.call_count == 4


def test_fail_iteration_succeeds_after_the_conflict_clears():
    doc = _session_doc(
        iteration_count=1, iterations=[{"index": 0, "status": "in_progress"}]
    )
    client = _stub_client(doc, put_failures=3)
    mgr = SessionManager(client, "bucket")

    mgr.fail_iteration("sess-1", "gemini", 0, "provider down")

    assert client.put_object.call_count == 4


def test_the_retry_budget_is_more_than_the_three_that_lost_images():
    """Four provider threads, eight conflicting writes per generation. Three
    attempts was thin enough that an image already generated and paid for was
    lost on the write."""
    assert MAX_RETRIES == 8


# --------------------------------------------------------------------------
# Round trips: the ETag comes from the read, and there is no second read
# --------------------------------------------------------------------------


def test_no_mutation_issues_a_head_object():
    """The regression guard for the round-trip reduction, and for the race it
    closed: between the get_object and the head_object another writer can land,
    so IfMatch used to guard a version the reader never read."""
    doc = _session_doc(
        iteration_count=1, iterations=[{"index": 0, "status": "in_progress"}]
    )
    for call in (
        lambda m: m.add_iteration("sess-1", "gemini", "bluer"),
        lambda m: m.complete_iteration("sess-1", "gemini", 0, "k.png"),
        lambda m: m.fail_iteration("sess-1", "gemini", 0, "boom"),
    ):
        client = _stub_client(doc)
        call(SessionManager(client, "bucket"))
        assert client.head_object.call_count == 0


def test_the_write_is_conditioned_on_the_etag_the_read_returned():
    client = _stub_client(_session_doc())
    mgr = SessionManager(client, "bucket")

    mgr.add_iteration("sess-1", "gemini", "bluer")

    assert client.put_object.call_args.kwargs["IfMatch"] == _READ_ETAG
    assert client.put_object.call_args.kwargs["IfMatch"] != _HEAD_ETAG


def test_each_retry_uses_the_etag_of_its_own_re_read():
    """A retry that re-reads but reuses the first ETag can never succeed."""
    etags = ['"e1"', '"e2"', '"e3"']
    client = _stub_client(_session_doc(), put_failures=2, read_etags=etags)
    mgr = SessionManager(client, "bucket")

    mgr.add_iteration("sess-1", "gemini", "bluer")

    used = [c.kwargs["IfMatch"] for c in client.put_object.call_args_list]
    assert used == etags


def test_a_mutation_costs_two_round_trips_not_three():
    client = _stub_client(_session_doc())
    mgr = SessionManager(client, "bucket")

    mgr.add_iteration("sess-1", "gemini", "bluer")

    total = (
        client.get_object.call_count
        + client.head_object.call_count
        + client.put_object.call_count
    )
    assert total == 2


# --------------------------------------------------------------------------
# Errors that are not conflicts
# --------------------------------------------------------------------------


def test_a_non_conflict_client_error_propagates_rather_than_retrying():
    """AccessDenied is not contention. Swallowing it as a conflict would burn
    the whole retry budget and then report the wrong failure."""
    client = _stub_client(_session_doc())
    client.put_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied"}}, "PutObject"
    )
    mgr = SessionManager(client, "bucket")

    with pytest.raises(ClientError) as excinfo:
        mgr.add_iteration("sess-1", "gemini", "bluer")

    assert excinfo.value.response["Error"]["Code"] == "AccessDenied"
    assert client.put_object.call_count == 1


def test_a_412_status_code_is_treated_as_a_conflict():
    client = _stub_client(_session_doc())
    calls = {"n": 0}

    def _put(**_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ClientError({"Error": {"Code": "412"}}, "PutObject")
        return {}

    client.put_object.side_effect = _put
    mgr = SessionManager(client, "bucket")

    assert mgr.add_iteration("sess-1", "gemini", "bluer") == 0
    assert calls["n"] == 2


def test_a_missing_session_is_a_value_error_not_a_concurrency_error():
    client = _stub_client(_session_doc())
    client.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey"}}, "GetObject"
    )
    mgr = SessionManager(client, "bucket")

    with pytest.raises(ValueError, match="not found"):
        mgr.add_iteration("missing", "gemini", "bluer")


# --------------------------------------------------------------------------
# Backoff
# --------------------------------------------------------------------------


def test_the_backoff_grows_and_stays_small_against_the_dispatch_budget(
    _no_real_sleeping,
):
    """A lock that sleeps for a meaningful slice of the dispatch budget has
    become the timeout it was meant to survive."""
    import config

    client = _stub_client(_session_doc(), put_failures=999)
    mgr = SessionManager(client, "bucket")

    with pytest.raises(ConcurrencyError):
        mgr.add_iteration("sess-1", "gemini", "bluer")

    waits = [c.args[0] for c in _no_real_sleeping.call_args_list]
    assert len(waits) == MAX_RETRIES - 1, "no sleep after the final attempt"
    # Strictly growing even at the jitter extremes: base*2**n + [0, base) has
    # a lower bound at n+1 of base*2**(n+1), above the upper bound at n of
    # base*(2**n + 1) for every n >= 1.
    assert waits == sorted(waits)
    assert waits[-1] > waits[0]
    assert sum(waits) < config.generate_dispatch_budget_seconds / 10


def test_the_backoff_is_jittered_so_conflicting_writers_do_not_re_collide():
    client = _stub_client(_session_doc(), put_failures=999)
    mgr = SessionManager(client, "bucket")
    observed = set()

    for _ in range(5):
        client.put_object.reset_mock()
        client.put_object.side_effect = _precondition_failed()
        with patch("jobs.manager.time.sleep") as sleep, pytest.raises(ConcurrencyError):
            mgr.add_iteration("sess-1", "gemini", "bluer")
        observed.add(tuple(c.args[0] for c in sleep.call_args_list))

    assert len(observed) > 1, "identical backoff every time means no jitter"


# --------------------------------------------------------------------------
# The typed session shape
# --------------------------------------------------------------------------


def test_session_state_marks_only_the_historically_absent_fields_optional():
    """Sessions written before visibility existed carry neither ownerId nor
    visibility, so asserting them required would assert a shape that records
    already in S3 do not have."""
    from jobs.manager import SessionState

    assert set(SessionState.__optional_keys__) == {"ownerId", "visibility"}
    assert {
        "sessionId",
        "status",
        "version",
        "prompt",
        "createdAt",
        "updatedAt",
        "models",
    } <= set(SessionState.__required_keys__)


def test_create_session_writes_every_key_the_typed_shape_declares():
    client = MagicMock()
    mgr = SessionManager(client, "bucket")

    mgr.create_session("a cat", ["gemini"], owner_id="u1", visibility="private")

    written = json.loads(client.put_object.call_args.kwargs["Body"])
    from jobs.manager import SessionState

    declared = set(SessionState.__required_keys__) | set(SessionState.__optional_keys__)
    assert set(written) == declared
