"""CircuitBreaker: stop calling a provider that keeps failing, then probe it with one call."""

import pytest
from llm_fakes import Clock

from sec_agent.llm.breaker import BreakerConfig, CircuitBreaker

CONFIG = BreakerConfig(failure_threshold=3, cooldown_seconds=30.0)


def _breaker(clock: Clock) -> CircuitBreaker:
    return CircuitBreaker(CONFIG, clock.monotonic)


def _fail(breaker: CircuitBreaker, times: int) -> None:
    for _ in range(times):
        assert breaker.acquire()
        breaker.failure()


def test_closed_breaker_lets_every_call_through() -> None:
    breaker = _breaker(Clock())
    assert breaker.state == "closed"
    assert breaker.acquire()
    assert breaker.acquire()


def test_opens_after_consecutive_failures_and_refuses_calls() -> None:
    breaker = _breaker(Clock())
    _fail(breaker, 2)
    assert breaker.state == "closed"
    _fail(breaker, 1)
    assert breaker.state == "open"
    assert not breaker.acquire()


def test_a_success_resets_the_failure_count() -> None:
    breaker = _breaker(Clock())
    _fail(breaker, 2)
    assert breaker.acquire()
    breaker.success()
    _fail(breaker, 2)
    assert breaker.state == "closed"


def test_after_the_cooldown_one_trial_call_is_let_through() -> None:
    clock = Clock()
    breaker = _breaker(clock)
    _fail(breaker, 3)
    clock.advance(29.9)
    assert not breaker.acquire()
    clock.advance(0.1)
    assert breaker.state == "half_open"
    assert breaker.acquire()
    assert not breaker.acquire(), "only one trial at a time"


def test_a_successful_trial_closes_the_breaker() -> None:
    clock = Clock()
    breaker = _breaker(clock)
    _fail(breaker, 3)
    clock.advance(30)
    assert breaker.acquire()
    breaker.success()
    assert breaker.state == "closed"
    assert breaker.acquire()


def test_a_failed_trial_opens_it_for_another_cooldown() -> None:
    clock = Clock()
    breaker = _breaker(clock)
    _fail(breaker, 3)
    clock.advance(30)
    assert breaker.acquire()
    breaker.failure()
    assert breaker.state == "open"
    clock.advance(29)
    assert not breaker.acquire()
    clock.advance(1)
    assert breaker.acquire()


def test_a_trial_that_was_not_used_can_be_taken_again() -> None:
    clock = Clock()
    breaker = _breaker(clock)
    _fail(breaker, 3)
    clock.advance(30)
    assert breaker.acquire()
    breaker.release()
    assert breaker.state == "half_open"
    assert breaker.acquire()


def test_trip_opens_at_once_for_the_given_time() -> None:
    clock = Clock()
    breaker = _breaker(clock)
    breaker.trip(120.0)
    assert breaker.state == "open"
    clock.advance(119)
    assert not breaker.acquire()
    clock.advance(1)
    assert breaker.acquire()


def test_trip_without_a_time_uses_the_cooldown() -> None:
    clock = Clock()
    breaker = _breaker(clock)
    breaker.trip()
    clock.advance(30)
    assert breaker.state == "half_open"


def test_a_trip_is_never_longer_than_the_longest_allowed() -> None:
    """A provider asking for a day's wait is probed again after the cap."""
    clock = Clock()
    config = BreakerConfig(failure_threshold=3, cooldown_seconds=30.0, max_open_seconds=600.0)
    breaker = CircuitBreaker(config, clock.monotonic)
    breaker.trip(86_400.0)
    clock.advance(599)
    assert breaker.state == "open"
    clock.advance(1)
    assert breaker.state == "half_open"


@pytest.mark.parametrize(
    "config",
    [
        {"failure_threshold": 0, "cooldown_seconds": 30.0},
        {"failure_threshold": 3, "cooldown_seconds": 0.0},
        {"failure_threshold": 3, "cooldown_seconds": 30.0, "max_open_seconds": 10.0},
    ],
)
def test_a_breaker_configuration_that_cannot_work_is_refused(config: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="breaker"):
        BreakerConfig(**config)  # pyright: ignore[reportArgumentType]
