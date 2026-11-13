"""Retry policy: exponential backoff with full jitter, and Retry-After from the server."""

import random
from datetime import UTC, datetime

import pytest

from sec_agent.edgar.retry import RetryPolicy, is_retryable, parse_retry_after


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_overload_and_server_errors_are_retried(status: int) -> None:
    assert is_retryable(status)


@pytest.mark.parametrize("status", [200, 301, 400, 401, 403, 404])
def test_other_statuses_are_not_retried(status: int) -> None:
    assert not is_retryable(status)


def test_delay_stays_inside_the_exponential_envelope() -> None:
    policy = RetryPolicy(max_attempts=6, base_delay=0.5, max_delay=4.0)
    for seed in range(200):
        rng = random.Random(seed)
        for attempt, ceiling in [(1, 0.5), (2, 1.0), (3, 2.0), (4, 4.0), (5, 4.0)]:
            assert 0.0 <= policy.delay(attempt, rng) <= ceiling


def test_delay_is_jittered() -> None:
    policy = RetryPolicy()
    delays = {policy.delay(3, random.Random(seed)) for seed in range(20)}
    assert len(delays) == 20


def test_delay_is_reproducible_with_a_seed() -> None:
    policy = RetryPolicy()
    assert policy.delay(2, random.Random(7)) == policy.delay(2, random.Random(7))


def test_delay_never_undercuts_retry_after() -> None:
    policy = RetryPolicy(base_delay=0.5, max_delay=30.0)
    for seed in range(50):
        assert policy.delay(1, random.Random(seed), retry_after=12.0) >= 12.0


@pytest.mark.parametrize(
    ("attempts", "base", "cap"), [(0, 0.5, 1.0), (1, -1.0, 1.0), (1, 2.0, 1.0)]
)
def test_rejects_invalid_policy(attempts: int, base: float, cap: float) -> None:
    with pytest.raises(ValueError, match=r"attempts|delay"):
        RetryPolicy(max_attempts=attempts, base_delay=base, max_delay=cap)


NOW = datetime(2026, 11, 13, 12, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("header", "seconds"),
    [
        ("5", 5.0),
        (" 120 ", 120.0),
        ("Fri, 13 Nov 2026 12:00:30 GMT", 30.0),
        ("Fri, 13 Nov 2026 11:59:00 GMT", 0.0),
        (None, None),
        ("", None),
        ("soon", None),
        ("-3", None),
    ],
)
def test_parse_retry_after(header: str | None, seconds: float | None) -> None:
    assert parse_retry_after(header, now=NOW) == seconds
