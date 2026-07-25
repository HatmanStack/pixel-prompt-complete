"""Tests for GET /pricing.

The endpoint exists so prices live in one place. Its job is to make the UI
incapable of advertising a number the backend does not enforce.
"""

from __future__ import annotations

import importlib
import json
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


def _get():
    from api.pricing import handle_pricing

    resp = handle_pricing({}, "corr-1")
    return resp, json.loads(resp["body"])


def test_returns_200_and_json():
    resp, _ = _get()
    assert resp["statusCode"] == 200
    assert resp["headers"]["Content-Type"] == "application/json"


def test_is_cacheable():
    """Every client fetches this on load; it changes rarely."""
    resp, _ = _get()
    assert "max-age" in resp["headers"]["Cache-Control"]


def test_exposes_credit_costs_matching_config():
    """The UI must not be able to show a cost the backend does not charge."""
    import config

    _, body = _get()
    assert body["creditCosts"]["generate"] == config.credits_per_generate
    assert body["creditCosts"]["refine"] == config.credits_per_refine
    assert body["creditCosts"]["outpaint"] == config.credits_per_outpaint


def test_generate_costs_four_times_a_refine():
    _, body = _get()
    assert body["creditCosts"]["generate"] == 4 * body["creditCosts"]["refine"]


def test_tiers_match_enforced_allotments():
    import config

    _, body = _get()
    tiers = {t["id"]: t for t in body["tiers"]}
    assert tiers["free"]["monthlyCredits"] == config.free_monthly_credits
    assert tiers["paid"]["monthlyCredits"] == config.paid_monthly_credits
    assert tiers["paid"]["priceUsdCents"] == config.paid_price_usd_cents


def test_only_advertises_tiers_the_backend_can_enforce():
    """Listing a plan resolve_tier cannot produce would sell a fiction."""
    _, body = _get()
    assert {t["id"] for t in body["tiers"]} == {"free", "paid"}


def test_free_tier_gets_all_four_models():
    """The decided pricing model: free sees all 4, so fan-out is not the lever."""
    _, body = _get()
    free = next(t for t in body["tiers"] if t["id"] == "free")
    assert free["allModels"] is True
    assert free["priceUsdCents"] == 0


def test_paid_renewal_is_stripe_anchored():
    """Paid credits renew on Stripe's 28-31 day cycle, not a fixed clock."""
    _, body = _get()
    paid = next(t for t in body["tiers"] if t["id"] == "paid")
    assert paid["renewal"] == "stripe_billing_period"


def test_price_is_env_tunable(monkeypatch):
    """A price experiment must be a config change, not a frontend rebuild."""
    monkeypatch.setenv("PAID_PRICE_USD_CENTS", "2900")
    import config

    importlib.reload(config)
    try:
        _, body = _get()
        paid = next(t for t in body["tiers"] if t["id"] == "paid")
        assert paid["priceUsdCents"] == 2900
    finally:
        monkeypatch.delenv("PAID_PRICE_USD_CENTS", raising=False)
        importlib.reload(config)


def test_reports_whether_credits_are_enforced():
    """A client showing credit balances needs to know if they mean anything."""
    import config

    _, body = _get()
    assert body["creditsEnabled"] == config.credits_enabled


def test_exposes_centi_credit_scale():
    """Costs are integers; the client needs the scale to render fractions."""
    _, body = _get()
    assert body["centiCreditsPerCredit"] == 100


def test_routes_through_lambda_handler():
    import lambda_function

    resp = lambda_function.lambda_handler(
        {
            "rawPath": "/pricing",
            "requestContext": {"http": {"method": "GET", "sourceIp": "1.2.3.4"}},
            "headers": {},
        },
        None,
    )
    assert resp["statusCode"] == 200
    assert "tiers" in json.loads(resp["body"])


def test_needs_no_authentication():
    """The upgrade modal renders before a user has an account."""
    import lambda_function

    resp = lambda_function.lambda_handler(
        {
            "rawPath": "/pricing",
            "requestContext": {"http": {"method": "GET", "sourceIp": "1.2.3.4"}},
            "headers": {},
        },
        None,
    )
    assert resp["statusCode"] == 200


# ---- Displayed price vs the price Stripe actually charges ----


def _reset():
    from api.pricing import reset_price_cache

    reset_price_cache()


def test_falls_back_to_config_when_billing_disabled():
    """A public endpoint must not depend on Stripe being reachable."""
    import config

    _reset()
    with patch.object(config, "billing_enabled", False):
        _, body = _get()
    paid = next(t for t in body["tiers"] if t["id"] == "paid")
    assert paid["priceUsdCents"] == config.paid_price_usd_cents


def test_uses_the_stripe_amount_when_available():
    """Stripe is the authority: it is what the customer is charged."""
    import config

    _reset()
    fake = MagicMock()
    fake.Price.retrieve.return_value = {"unit_amount": 2900}
    with (
        patch.object(config, "billing_enabled", True),
        patch.object(config, "stripe_price_id", "price_123"),
        patch("billing.stripe_client.get_stripe", return_value=fake),
    ):
        _, body = _get()
    paid = next(t for t in body["tiers"] if t["id"] == "paid")
    assert paid["priceUsdCents"] == 2900
    _reset()


def test_stripe_amount_wins_over_a_mismatched_config():
    """Config saying $19 while Stripe charges $29 must not show $19."""
    import config

    _reset()
    fake = MagicMock()
    fake.Price.retrieve.return_value = {"unit_amount": 2900}
    with (
        patch.object(config, "billing_enabled", True),
        patch.object(config, "stripe_price_id", "price_123"),
        patch.object(config, "paid_price_usd_cents", 1900),
        patch("billing.stripe_client.get_stripe", return_value=fake),
    ):
        _, body = _get()
    paid = next(t for t in body["tiers"] if t["id"] == "paid")
    assert paid["priceUsdCents"] == 2900, "must never advertise less than Stripe charges"
    _reset()


def test_stripe_failure_degrades_to_config_not_an_error():
    """Stripe being down must not take the pricing endpoint with it."""
    import config

    _reset()
    fake = MagicMock()
    fake.Price.retrieve.side_effect = RuntimeError("stripe down")
    with (
        patch.object(config, "billing_enabled", True),
        patch.object(config, "stripe_price_id", "price_123"),
        patch("billing.stripe_client.get_stripe", return_value=fake),
    ):
        resp, body = _get()
    assert resp["statusCode"] == 200
    paid = next(t for t in body["tiers"] if t["id"] == "paid")
    assert paid["priceUsdCents"] == config.paid_price_usd_cents
    _reset()


def test_stripe_price_is_cached_across_requests():
    """/pricing is hit on every page load; do not call Stripe each time."""
    import config

    _reset()
    fake = MagicMock()
    fake.Price.retrieve.return_value = {"unit_amount": 2900}
    with (
        patch.object(config, "billing_enabled", True),
        patch.object(config, "stripe_price_id", "price_123"),
        patch("billing.stripe_client.get_stripe", return_value=fake),
    ):
        _get()
        _get()
        _get()
    assert fake.Price.retrieve.call_count == 1
    _reset()


def test_stripe_outage_is_cached_not_retried_every_request():
    """A public endpoint must not hammer a failing upstream.

    /pricing is fetched on every page load, so retrying Stripe per request
    during an outage means every visitor blocks on the same failing call.
    """
    import config

    _reset()
    fake = MagicMock()
    fake.Price.retrieve.side_effect = RuntimeError("stripe down")
    with (
        patch.object(config, "billing_enabled", True),
        patch.object(config, "stripe_price_id", "price_123"),
        patch("billing.stripe_client.get_stripe", return_value=fake),
    ):
        for _ in range(5):
            resp, body = _get()
            assert resp["statusCode"] == 200
    assert fake.Price.retrieve.call_count == 1, "failure should be cached too"
    _reset()


def test_missing_unit_amount_is_also_cached():
    import config

    _reset()
    fake = MagicMock()
    fake.Price.retrieve.return_value = {"unit_amount": None}
    with (
        patch.object(config, "billing_enabled", True),
        patch.object(config, "stripe_price_id", "price_123"),
        patch("billing.stripe_client.get_stripe", return_value=fake),
    ):
        _get()
        _get()
    assert fake.Price.retrieve.call_count == 1
    _reset()
