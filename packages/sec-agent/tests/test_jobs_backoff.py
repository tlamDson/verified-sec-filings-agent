"""Retry delay: exponential, capped, full jitter, reproducible with a seed."""

import random

import pytest

from sec_agent.jobs.backoff import retry_delay


class _Top(random.Random):
    """Always draws the top of the jitter range, exposing the ceiling."""

    def random(self) -> float:
        return 1.0


def test_ceiling_doubles_per_attempt_then_caps() -> None:
    top = _Top()
    ceilings = [retry_delay(a, base=2.0, cap=20.0, rng=top) for a in range(1, 6)]
    assert ceilings == [2.0, 4.0, 8.0, 16.0, 20.0]


def test_full_jitter_stays_within_zero_and_ceiling() -> None:
    rng = random.Random(42)
    for attempt in range(1, 12):
        delay = retry_delay(attempt, base=1.0, cap=60.0, rng=rng)
        assert 0.0 <= delay <= min(60.0, 2.0 ** (attempt - 1))


def test_same_seed_same_delays() -> None:
    first = [retry_delay(a, base=1.0, cap=60.0, rng=random.Random(7)) for a in range(1, 6)]
    second = [retry_delay(a, base=1.0, cap=60.0, rng=random.Random(7)) for a in range(1, 6)]
    assert first == second


def test_huge_attempt_number_does_not_overflow() -> None:
    assert retry_delay(10_000, base=1.0, cap=30.0, rng=random.Random(1)) <= 30.0


@pytest.mark.parametrize(("attempt", "base", "cap"), [(0, 1.0, 1.0), (1, 0.0, 1.0), (1, 2.0, 1.0)])
def test_rejects_invalid_arguments(attempt: int, base: float, cap: float) -> None:
    with pytest.raises(ValueError, match="retry_delay"):
        retry_delay(attempt, base=base, cap=cap, rng=random.Random(0))
