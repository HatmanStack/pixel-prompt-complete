"""Tests for users.repository.UserRepository using moto."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from users.repository import UserRepository

TABLE = "pixel-prompt-users"


@pytest.fixture
def users_table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield TABLE, ddb


def _repo(users_table):
    return UserRepository(users_table[0], dynamodb_resource=users_table[1])


def test_get_or_create_user(users_table):
    repo = _repo(users_table)
    first = repo.get_or_create_user("u1", email="u@example.com")
    assert first["userId"] == "u1"
    assert first["tier"] == "free"
    second = repo.get_or_create_user("u1")
    assert second["userId"] == "u1"


def test_increment_generate_within_window(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    ok1, item1 = repo.increment_generate("u1", 3600, 5, now)
    ok2, item2 = repo.increment_generate("u1", 3600, 5, now + 10)
    assert ok1 and ok2
    assert int(item2["generateCount"]) == 2


def test_increment_generate_limit_block(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    ok, _ = repo.increment_generate("u1", 3600, 1, now)
    assert ok
    ok2, item = repo.increment_generate("u1", 3600, 1, now + 5)
    assert not ok2
    assert int(item["generateCount"]) == 1


def test_increment_generate_resets_window(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    repo.increment_generate("u1", 3600, 1, now)
    # Advance past window.
    later = now + 4000
    ok, item = repo.increment_generate("u1", 3600, 1, later)
    assert ok
    assert int(item["generateCount"]) == 1
    assert int(item["windowStart"]) >= later - 1


def test_increment_refine_independent_of_generate(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    repo.increment_generate("u1", 3600, 5, now)
    ok, item = repo.increment_refine("u1", 3600, 5, now)
    assert ok
    assert int(item["refineCount"]) == 1
    assert int(item["generateCount"]) == 1


def test_increment_daily(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    repo.get_or_create_user("u1")
    ok, item = repo.increment_daily("u1", 86400, 3, now)
    assert ok
    assert int(item["dailyCount"]) == 1


def test_set_tier_paid_and_free(users_table):
    repo = _repo(users_table)
    repo.get_or_create_user("u1")
    repo.set_tier("u1", "paid", stripeSubscriptionId="sub_1", subscriptionStatus="active")
    item = repo.get_user("u1")
    assert item["tier"] == "paid"
    assert item["stripeSubscriptionId"] == "sub_1"
    repo.set_tier("u1", "free")
    assert repo.get_user("u1")["tier"] == "free"


def test_set_stripe_customer_id_idempotent(users_table):
    repo = _repo(users_table)
    repo.get_or_create_user("u1")
    repo.set_stripe_customer_id("u1", "cus_1")
    repo.set_stripe_customer_id("u1", "cus_1")
    assert repo.get_user("u1")["stripeCustomerId"] == "cus_1"


def test_guest_item_uses_ttl(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    item = repo.upsert_guest("tok1", "iphash", now + 3900)
    assert item["userId"] == "guest#tok1"
    assert int(item["ttl"]) == now + 3900


def test_increment_guest_generate(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    repo.upsert_guest("tok1", "ip", now + 3900)
    ok, _ = repo.increment_guest_generate("tok1", 1, 3600, now)
    assert ok
    ok2, _ = repo.increment_guest_generate("tok1", 1, 3600, now + 1)
    assert not ok2


def test_global_guest_counter_atomic(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    for _ in range(3):
        ok, _ = repo.increment_global_guest(5, 3600, now)
        assert ok
    # 4 more, should block after 5.
    results = [repo.increment_global_guest(5, 3600, now)[0] for _ in range(4)]
    assert results.count(True) == 2
    assert results.count(False) == 2


def test_touch_quota_window_resets(users_table):
    repo = _repo(users_table)
    now = 1_000_000
    repo.increment_generate("u1", 3600, 5, now)
    # After window expiry, touch should zero counters.
    later = now + 4000
    item = repo.touch_quota_window("u1", 3600, later)
    assert int(item["generateCount"]) == 0
    assert int(item["windowStart"]) >= later - 1


# ---------------------------------------------------------------------------
# scan_users paging and cost bound
# ---------------------------------------------------------------------------


def _seed_mixed(repo, real=30, synthetic=200):
    """Real users interleaved with the synthetic records that outnumber them.

    Synthetic keys are what the admin scan filters client-side, and on a live
    table there are vastly more of them than real users -- which is why a
    request for a page of users could scan the whole table.
    """
    for i in range(max(real, synthetic)):
        if i < real:
            repo._table.put_item(Item={"userId": f"user-{i:03d}", "tier": "free"})
        if i < synthetic:
            prefix = ("guest#", "spend#", "anon#")[i % 3]
            repo._table.put_item(Item={"userId": f"{prefix}{i:03d}"})


@pytest.mark.parametrize(
    "synthetic,limit",
    [
        # The plan's scenario: heavy synthetic load, a page of ten.
        (200, 10),
        # Two shapes where the OLD implementation demonstrably loses users,
        # measured rather than assumed: it drops 1 of 30 at (200, 3) and 6 of
        # 30 at (15, 7). Whether the defect bites depends on whether the final
        # page contributes MORE users than are still needed, which depends on
        # the filtered density -- so a single shape is not enough to catch it.
        (200, 3),
        (15, 7),
    ],
)
def test_scan_users_paging_neither_skips_nor_repeats(users_table, synthetic, limit):
    """The assertion the old implementation fails.

    It returned collected[:limit] paired with the LastEvaluatedKey of the page
    whose SURPLUS items had just been dropped, so feeding that key back began
    after the items it discarded -- they were never returned to anyone.
    """
    repo = _repo(users_table)
    _seed_mixed(repo, synthetic=synthetic)

    seen = []
    cursor = None
    # max_pages is raised above its default here on purpose: this test is
    # about paging correctness, and the default is a cost bound with its own
    # test below.
    for _ in range(60):
        page, cursor = repo.scan_users(limit=limit, last_key=cursor, max_pages=50)
        seen.extend(item["userId"] for item in page)
        if not cursor:
            break
    else:
        raise AssertionError("paging did not terminate")

    assert len(seen) == 30, "every real user must be returned exactly once"
    assert len(set(seen)) == 30, "no repeats"
    assert set(seen) == {f"user-{i:03d}" for i in range(30)}


def test_scan_users_first_page_returns_exactly_the_limit(users_table):
    repo = _repo(users_table)
    _seed_mixed(repo)

    page, cursor = repo.scan_users(limit=10, max_pages=50)

    assert len(page) == 10
    assert cursor is not None
    assert all(not item["userId"].startswith(("guest#", "spend#", "anon#")) for item in page)


def test_scan_users_second_page_does_not_overlap_the_first(users_table):
    repo = _repo(users_table)
    _seed_mixed(repo)

    first, cursor = repo.scan_users(limit=10, max_pages=50)
    second, _ = repo.scan_users(limit=10, last_key=cursor, max_pages=50)

    first_ids = [i["userId"] for i in first]
    second_ids = [i["userId"] for i in second]
    assert len(second_ids) == 10
    assert set(first_ids).isdisjoint(second_ids)


def test_scan_users_stops_at_the_page_ceiling(users_table):
    """A cost bound, not a correctness bound: a short page is a normal
    DynamoDB result and the admin UI already pages."""
    repo = _repo(users_table)
    _seed_mixed(repo, real=1, synthetic=300)

    calls = {"n": 0}
    real_scan = repo._table.scan

    def _counting_scan(**kwargs):
        calls["n"] += 1
        return real_scan(**kwargs)

    repo._table.scan = _counting_scan
    page, cursor = repo.scan_users(limit=50, max_pages=3)

    assert calls["n"] == 3, "one admin request must not be able to scan the table"
    assert len(page) < 50
    assert cursor is not None, "a truncated scan must say where to resume"


def test_scan_users_exhausting_the_table_returns_no_cursor(users_table):
    repo = _repo(users_table)
    _seed_mixed(repo, real=3, synthetic=3)

    page, cursor = repo.scan_users(limit=50)

    assert len(page) == 3
    assert cursor is None


def test_scan_users_cursor_is_the_last_returned_item_not_the_last_scanned(users_table):
    """The cursor must key off an item the caller actually saw.

    Seeded at (15 synthetic, limit 7) because that is a shape where the final
    page overshoots, so the last item RETURNED and the last item SCANNED are
    different -- at other densities the two coincide and the assertion cannot
    fail.
    """
    repo = _repo(users_table)
    _seed_mixed(repo, synthetic=15)

    page, cursor = repo.scan_users(limit=7, max_pages=50)

    assert cursor == {"userId": page[-1]["userId"]}
