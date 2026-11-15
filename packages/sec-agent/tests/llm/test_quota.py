"""Per-provider quota: requests per minute and day, tokens per day, in memory and in Postgres.

Both stores must give the same answers; the Postgres one is shared by every API replica.
"""

import datetime as dt
import threading
from collections.abc import Iterator

import psycopg
import pytest
from llm_fakes import T0

from sec_agent.llm.quota import (
    MemoryQuotaStore,
    QuotaLimits,
    QuotaStore,
    QuotaUsage,
    day_window,
    minute_window,
)
from sec_agent.llm.quota_postgres import PostgresQuotaStore

MINUTE = dt.timedelta(minutes=1)
DAY = dt.timedelta(days=1)


@pytest.fixture(params=["memory", "postgres"])
def store(request: pytest.FixtureRequest) -> Iterator[QuotaStore]:
    if request.param == "memory":
        yield MemoryQuotaStore()
        return
    with PostgresQuotaStore.connect(request.getfixturevalue("llm_db")) as pg:
        yield pg


def test_windows_are_utc_minutes_and_days() -> None:
    at = dt.datetime(2026, 11, 13, 23, 59, 42, tzinfo=dt.timezone(dt.timedelta(hours=-5)))
    assert minute_window(at) == dt.datetime(2026, 11, 14, 4, 59, tzinfo=dt.UTC)
    assert day_window(at) == dt.datetime(2026, 11, 14, tzinfo=dt.UTC)


def test_a_time_without_a_zone_is_refused() -> None:
    with pytest.raises(ValueError, match="time zone"):
        minute_window(dt.datetime(2026, 11, 13, 9, 30))


def test_limits_must_be_positive() -> None:
    with pytest.raises(ValueError, match="requests_per_minute"):
        QuotaLimits(requests_per_minute=0)


def test_requests_per_minute_fill_up_and_free_up_the_next_minute(store: QuotaStore) -> None:
    limits = QuotaLimits(requests_per_minute=2)
    assert store.reserve("a", limits, T0)
    assert store.reserve("a", limits, T0 + dt.timedelta(seconds=20))
    assert not store.reserve("a", limits, T0 + dt.timedelta(seconds=40))
    assert store.reserve("a", limits, T0 + MINUTE)


def test_requests_per_day_span_minutes_and_reset_the_next_day(store: QuotaStore) -> None:
    limits = QuotaLimits(requests_per_day=2)
    assert store.reserve("a", limits, T0)
    assert store.reserve("a", limits, T0 + 5 * MINUTE)
    assert not store.reserve("a", limits, T0 + 10 * MINUTE)
    assert store.reserve("a", limits, T0 + DAY)


def test_a_refused_request_is_not_counted(store: QuotaStore) -> None:
    limits = QuotaLimits(requests_per_minute=1, requests_per_day=5)
    assert store.reserve("a", limits, T0)
    assert not store.reserve("a", limits, T0)
    assert store.usage("a", T0) == QuotaUsage(minute_requests=1, day_requests=1, day_tokens=0)


def test_tokens_per_day_close_the_provider_once_spent(store: QuotaStore) -> None:
    limits = QuotaLimits(tokens_per_day=1000)
    assert store.reserve("a", limits, T0)
    store.settle("a", T0, held=0, used=999)
    assert store.reserve("a", limits, T0)
    store.settle("a", T0 + MINUTE, held=0, used=1)
    assert not store.reserve("a", limits, T0 + 2 * MINUTE)
    assert store.usage("a", T0 + 2 * MINUTE).day_tokens == 1000
    assert store.reserve("a", limits, T0 + DAY)


def test_a_call_holds_its_token_bound_so_calls_in_flight_cannot_overspend(
    store: QuotaStore,
) -> None:
    """The count moves before the call is made, not when it returns."""
    limits = QuotaLimits(tokens_per_day=1000)
    assert store.reserve("a", limits, T0, tokens=600)
    assert not store.reserve("a", limits, T0, tokens=600), "600 held + 600 would pass 1000"
    assert store.usage("a", T0) == QuotaUsage(minute_requests=1, day_requests=1, day_tokens=600)
    store.settle("a", T0, held=600, used=250)
    assert store.usage("a", T0).day_tokens == 250, "the unused part of the hold is returned"
    assert store.reserve("a", limits, T0, tokens=600)
    assert store.usage("a", T0).day_tokens == 850


def test_a_call_larger_than_what_is_left_of_the_day_is_refused(store: QuotaStore) -> None:
    limits = QuotaLimits(tokens_per_day=1000)
    store.settle("a", T0, held=0, used=900)
    assert not store.reserve("a", limits, T0, tokens=101)
    assert store.reserve("a", limits, T0, tokens=100)
    assert store.usage("a", T0).day_tokens == 1000
    assert not store.reserve("a", limits, T0, tokens=0), "a spent day takes no call at all"


def test_a_hold_is_settled_on_the_day_it_was_taken(store: QuotaStore) -> None:
    """A call that starts before midnight UTC and ends after belongs to the day it started."""
    limits = QuotaLimits(tokens_per_day=1000)
    assert store.reserve("a", limits, T0, tokens=500)
    store.settle("a", T0, held=500, used=120)
    assert store.usage("a", T0).day_tokens == 120
    assert store.usage("a", T0 + DAY).day_tokens == 0


def test_a_call_that_used_more_than_it_held_is_charged_what_it_used(store: QuotaStore) -> None:
    limits = QuotaLimits(tokens_per_day=1000)
    assert store.reserve("a", limits, T0, tokens=100)
    store.settle("a", T0, held=100, used=1200)
    assert store.usage("a", T0).day_tokens == 1200
    assert not store.reserve("a", limits, T0, tokens=1)


def test_settling_never_takes_the_count_below_zero(store: QuotaStore) -> None:
    store.settle("a", T0, held=500, used=0)
    assert store.usage("a", T0).day_tokens == 0


def test_a_hold_is_kept_even_without_a_token_limit(store: QuotaStore) -> None:
    assert store.reserve("a", QuotaLimits(), T0, tokens=10_000_000)
    assert store.usage("a", T0).day_tokens == 10_000_000


def test_without_limits_every_request_passes_and_is_still_counted(store: QuotaStore) -> None:
    for _ in range(3):
        assert store.reserve("a", QuotaLimits(), T0)
    assert store.usage("a", T0) == QuotaUsage(minute_requests=3, day_requests=3, day_tokens=0)


def test_providers_are_counted_apart(store: QuotaStore) -> None:
    limits = QuotaLimits(requests_per_day=1)
    assert store.reserve("a", limits, T0)
    assert store.reserve("b", limits, T0)
    assert not store.reserve("a", limits, T0)
    assert store.usage("b", T0).day_requests == 1
    assert store.usage("never-called", T0) == QuotaUsage(0, 0, 0)


def test_replicas_share_one_count_and_never_overspend(llm_db: str) -> None:
    """Twelve connections race for a daily quota of five: exactly five get a request."""
    limits = QuotaLimits(requests_per_day=5)
    granted: list[bool] = []
    barrier = threading.Barrier(12)

    def replica() -> None:
        with PostgresQuotaStore.connect(llm_db) as pg:
            barrier.wait()
            granted.append(pg.reserve("shared", limits, T0))

    threads = [threading.Thread(target=replica) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(granted) == [False] * 7 + [True] * 5
    with PostgresQuotaStore.connect(llm_db) as pg:
        assert pg.usage("shared", T0).day_requests == 5


def test_replicas_racing_for_the_last_tokens_never_overspend_them(llm_db: str) -> None:
    """Twelve connections each hold 300 of a day's 1000 tokens: exactly three fit."""
    limits = QuotaLimits(tokens_per_day=1000)
    granted: list[bool] = []
    barrier = threading.Barrier(12)

    def replica() -> None:
        with PostgresQuotaStore.connect(llm_db) as pg:
            barrier.wait()
            granted.append(pg.reserve("shared", limits, T0, tokens=300))

    threads = [threading.Thread(target=replica) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(granted) == [False] * 9 + [True] * 3
    with PostgresQuotaStore.connect(llm_db) as pg:
        assert pg.usage("shared", T0) == QuotaUsage(3, 3, 900)


def test_old_minute_rows_are_pruned(llm_db: str) -> None:
    with PostgresQuotaStore.connect(llm_db) as pg:
        pg.reserve("a", QuotaLimits(), T0)
        pg.reserve("a", QuotaLimits(), T0 + 3 * DAY)
    with psycopg.connect(llm_db) as conn:
        rows = conn.execute(
            "SELECT window_kind, window_start FROM llm_usage WHERE provider = 'a' ORDER BY 1, 2"
        ).fetchall()
    assert rows == [
        ("day", day_window(T0)),
        ("day", day_window(T0 + 3 * DAY)),
        ("minute", minute_window(T0 + 3 * DAY)),
    ]
