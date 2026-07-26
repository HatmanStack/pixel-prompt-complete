"""The 18+ gate required by the provider terms.

Google allows its API only where the calling service is not "likely to be
accessed by" individuals under 18. That is a harder test than an affirmation,
and a public URL with a no-account guest tier that asks nothing does not meet
it. This is the asking.

The affirmation is recorded server-side rather than kept in localStorage. It is
still a self-declaration -- every age gate on the open web is -- but a recorded
one is evidence we asked, and a client-only one is not.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFRONT_DOMAIN", "test.cloudfront.net")

from users.tier import TierContext


@pytest.fixture
def repo():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="t",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        from users.repository import UserRepository

        yield UserRepository("t", dynamodb_resource=ddb)


def _ctx(tier="guest", uid=None):
    return TierContext(
        tier=tier,
        user_id=uid or f"{tier}#tok1",
        email=None,
        is_authenticated=tier in ("free", "paid"),
        guest_token_id="tok1" if tier == "guest" else None,
        issue_guest_cookie=False,
    )


# --- storage -----------------------------------------------------------------


def test_affirmation_is_remembered(repo):
    assert repo.has_affirmed_age("guest#tok1") is False
    repo.record_age_affirmation("guest#tok1", 1000)
    assert repo.has_affirmed_age("guest#tok1") is True


def test_affirmation_keeps_the_first_timestamp(repo):
    """Written only if absent, so this records when they answered, not when they last asked."""
    repo.record_age_affirmation("guest#tok1", 1000)
    repo.record_age_affirmation("guest#tok1", 5000)
    assert repo.get_user("guest#tok1")["ageAffirmedAt"] == 1000


def test_a_repeat_affirmation_is_not_an_error(repo):
    """Two concurrent first requests race here; the loser is not a failure."""
    repo.record_age_affirmation("guest#tok1", 1000)
    repo.record_age_affirmation("guest#tok1", 1001)  # must not raise


def test_affirming_does_not_extend_an_existing_guest_ttl(repo):
    """The gate must not become a way to keep a guest record alive forever."""
    repo.upsert_guest("tok1", "iphash", 4242)
    repo.record_age_affirmation("guest#tok1", 1000, ttl=999999)
    assert repo.get_user("guest#tok1")["ttl"] == 4242


def test_tiers_do_not_share_an_affirmation(repo):
    """user_id already namespaces guest#, anon# and Cognito subs apart."""
    repo.record_age_affirmation("guest#tok1", 1000)
    assert repo.has_affirmed_age("anon#tok1") is False
    assert repo.has_affirmed_age("tok1") is False


# --- the gate ----------------------------------------------------------------


def test_a_first_time_caller_is_asked():
    import lambda_function as lf

    mock_repo = MagicMock()
    mock_repo.has_affirmed_age.return_value = False
    with patch.object(lf, "_user_repo", mock_repo):
        err = lf._enforce_age_gate(_ctx(), {})

    assert err is not None
    assert err["statusCode"] == 403
    assert "AGE_VERIFICATION_REQUIRED" in err["body"]


def test_affirming_lets_the_request_through_and_is_recorded():
    import lambda_function as lf

    mock_repo = MagicMock()
    mock_repo.has_affirmed_age.return_value = False
    with patch.object(lf, "_user_repo", mock_repo):
        err = lf._enforce_age_gate(_ctx(), {"ageAffirmed": True})

    assert err is None
    mock_repo.record_age_affirmation.assert_called_once()


def test_a_returning_caller_is_not_asked_again():
    import lambda_function as lf

    mock_repo = MagicMock()
    mock_repo.has_affirmed_age.return_value = True
    with patch.object(lf, "_user_repo", mock_repo):
        assert lf._enforce_age_gate(_ctx(), {}) is None


@pytest.mark.parametrize("value", [False, "true", "yes", 1, None, "1"])
def test_only_a_real_boolean_true_counts(value):
    """A truthy string must not read as consent."""
    import lambda_function as lf

    mock_repo = MagicMock()
    mock_repo.has_affirmed_age.return_value = False
    with patch.object(lf, "_user_repo", mock_repo):
        err = lf._enforce_age_gate(_ctx(), {"ageAffirmed": value})

    assert err is not None, f"{value!r} was accepted as an affirmation"


def test_an_unreachable_store_re_prompts_rather_than_blocking_or_allowing():
    """Neither fail-open nor fail-closed: ask again.

    Failing open serves minors on a DynamoDB blip. Failing closed takes the
    site down on one. Not being able to recall that someone answered is a
    reason to repeat the question, and the answer still gets them through.
    """
    import lambda_function as lf

    mock_repo = MagicMock()
    mock_repo.has_affirmed_age.side_effect = RuntimeError("dynamo down")
    with patch.object(lf, "_user_repo", mock_repo):
        blocked = lf._enforce_age_gate(_ctx(), {})
        allowed = lf._enforce_age_gate(_ctx(), {"ageAffirmed": True})

    assert blocked["statusCode"] == 403
    assert allowed is None, "answering must work even when the store is down"


def test_a_failed_write_does_not_deny_a_caller_who_answered():
    import lambda_function as lf

    mock_repo = MagicMock()
    mock_repo.has_affirmed_age.return_value = False
    mock_repo.record_age_affirmation.side_effect = RuntimeError("dynamo down")
    with patch.object(lf, "_user_repo", mock_repo):
        assert lf._enforce_age_gate(_ctx(), {"ageAffirmed": True}) is None


def test_guest_affirmations_carry_a_ttl_but_account_ones_do_not():
    """Guest rows expire; an account's affirmation should outlive a window."""
    import lambda_function as lf

    for tier, expect_ttl in (("guest", True), ("anon", True), ("paid", False)):
        mock_repo = MagicMock()
        mock_repo.has_affirmed_age.return_value = False
        with patch.object(lf, "_user_repo", mock_repo):
            lf._enforce_age_gate(_ctx(tier), {"ageAffirmed": True})
        ttl = mock_repo.record_age_affirmation.call_args.args[2]
        assert (ttl is not None) is expect_ttl, tier


def test_the_gate_is_skipped_when_there_is_no_repo():
    """Open-source runs without a users table must not be bricked by this."""
    import lambda_function as lf

    with patch.object(lf, "_user_repo", None):
        assert lf._enforce_age_gate(_ctx(), {}) is None


# --- wiring ------------------------------------------------------------------


def test_the_flag_defaults_on(monkeypatch):
    """Unlike every other feature flag, because the provider terms require it."""
    import importlib

    import config

    monkeypatch.delenv("AGE_GATE_ENABLED", raising=False)
    monkeypatch.setenv("AUTH_ENABLED", "false")
    cfg = importlib.reload(config)
    try:
        assert cfg.age_gate_enabled is True
    finally:
        importlib.reload(config)


def test_generate_is_refused_before_any_provider_is_called():
    """The refusal must precede dispatch, or we pay for the ungated request."""
    import json

    import lambda_function as lf
    from users.quota import QuotaResult

    with (
        patch("config.age_gate_enabled", True),
        patch("config.auth_enabled", False),
        patch.object(lf, "_user_repo") as mock_repo,
        patch.object(lf, "enforce_quota") as mock_quota,
        patch.object(lf, "_executor") as mock_exec,
        patch.object(lf, "session_manager") as mock_sm,
    ):
        mock_repo.has_affirmed_age.return_value = False
        mock_quota.return_value = QuotaResult(allowed=True, reason=None, reset_at=0)
        resp = lf.handle_generate(
            {
                "body": json.dumps({"prompt": "a cat"}),
                "requestContext": {"http": {"sourceIp": "1.2.3.4"}},
                "headers": {},
            },
            "corr-age",
        )

    assert resp["statusCode"] == 403
    assert "AGE_VERIFICATION_REQUIRED" in resp["body"]
    mock_exec.submit.assert_not_called()
    mock_sm.create_session.assert_not_called()
