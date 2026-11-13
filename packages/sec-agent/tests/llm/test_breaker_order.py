"""CircuitBreaker with calls in flight: an outcome that arrives late is weighed by when
its call was sent.

A call sent before the breaker opened says nothing about the provider afterwards: its late
success must not close the breaker and its late failure must not replace the wait. A 429
is honoured whenever it arrives, and only ever lengthens a wait.
"""

from llm_fakes import Clock

from sec_agent.llm.breaker import BreakerConfig, CircuitBreaker, Permit

CONFIG = BreakerConfig(failure_threshold=3, cooldown_seconds=30.0)


def _breaker(clock: Clock) -> CircuitBreaker:
    return CircuitBreaker(CONFIG, clock.monotonic)


def _sent(breaker: CircuitBreaker) -> Permit:
    permit = breaker.acquire()
    assert permit is not None
    return permit


def _fail(breaker: CircuitBreaker, times: int) -> None:
    for _ in range(times):
        breaker.failure(_sent(breaker))


def test_a_success_sent_before_the_breaker_opened_does_not_close_it() -> None:
    clock = Clock()
    breaker = _breaker(clock)
    slow = _sent(breaker)
    _fail(breaker, 3)
    breaker.success(slow)
    assert breaker.state == "open"
    assert breaker.acquire() is None
    clock.advance(30)
    assert breaker.state == "half_open", "the wait is the one the failures started"


def test_a_success_sent_before_a_429_does_not_cancel_the_wait_it_asked() -> None:
    clock = Clock()
    breaker = _breaker(clock)
    slow, limited = _sent(breaker), _sent(breaker)
    breaker.trip(limited, 600.0)
    breaker.success(slow)
    clock.advance(599)
    assert breaker.state == "open"
    clock.advance(1)
    assert breaker.state == "half_open"


def test_a_failure_sent_before_a_429_does_not_replace_its_wait_with_the_cooldown() -> None:
    clock = Clock()
    breaker = _breaker(clock)
    slow, limited = _sent(breaker), _sent(breaker)
    breaker.trip(limited, 600.0)
    clock.advance(10)
    breaker.failure(slow)
    clock.advance(30)  # the 30 s cooldown a failure would have started is over
    assert breaker.state == "open"
    clock.advance(559)
    assert breaker.state == "open"
    clock.advance(1)
    assert breaker.state == "half_open"


def test_a_second_429_never_shortens_a_wait_already_running() -> None:
    clock = Clock()
    breaker = _breaker(clock)
    first, short, bare = _sent(breaker), _sent(breaker), _sent(breaker)
    breaker.trip(first, 600.0)
    breaker.trip(short, 5.0)
    breaker.trip(bare)  # no Retry-After: the cooldown
    clock.advance(599)
    assert breaker.state == "open"
    clock.advance(1)
    assert breaker.state == "half_open"


def test_a_later_429_that_asks_for_longer_lengthens_the_wait() -> None:
    clock = Clock()
    breaker = _breaker(clock)
    first, longer = _sent(breaker), _sent(breaker)
    breaker.trip(first, 5.0)
    clock.advance(1)
    breaker.trip(longer, 600.0)
    clock.advance(599)
    assert breaker.state == "open"
    clock.advance(1)
    assert breaker.state == "half_open"


def test_a_late_outcome_does_not_decide_the_trial_that_is_out() -> None:
    clock = Clock()
    breaker = _breaker(clock)
    slow_ok, slow_down = _sent(breaker), _sent(breaker)
    _fail(breaker, 3)
    clock.advance(30)
    trial = _sent(breaker)
    breaker.success(slow_ok)
    assert breaker.state == "half_open", "only the trial can close the breaker"
    assert breaker.acquire() is None, "the trial is still out"
    breaker.failure(slow_down)
    assert breaker.state == "half_open", "only the trial can open it again"
    assert breaker.acquire() is None
    breaker.success(trial)
    assert breaker.state == "closed"


def test_a_failed_trial_still_opens_the_breaker_after_late_outcomes() -> None:
    clock = Clock()
    breaker = _breaker(clock)
    slow = _sent(breaker)
    _fail(breaker, 3)
    clock.advance(30)
    trial = _sent(breaker)
    breaker.success(slow)
    breaker.failure(trial)
    assert breaker.state == "open"
    clock.advance(29)
    assert breaker.acquire() is None
    clock.advance(1)
    assert breaker.acquire() is not None


def test_a_429_that_arrives_while_a_trial_is_out_is_honoured_over_the_trial() -> None:
    """The provider's own word, valid from when it arrives: the trial's success is then
    the stale outcome."""
    clock = Clock()
    breaker = _breaker(clock)
    limited = _sent(breaker)
    _fail(breaker, 3)
    clock.advance(30)
    trial = _sent(breaker)
    breaker.trip(limited, 120.0)
    breaker.success(trial)
    assert breaker.state == "open"
    clock.advance(120)
    assert breaker.state == "half_open"
    breaker.success(_sent(breaker))
    assert breaker.state == "closed"


def test_a_late_release_does_not_free_a_trial_another_call_holds() -> None:
    clock = Clock()
    breaker = _breaker(clock)
    slow = _sent(breaker)
    _fail(breaker, 3)
    clock.advance(30)
    _sent(breaker)  # the trial
    breaker.release(slow)
    assert breaker.acquire() is None, "still one trial at a time"


def test_a_failure_sent_before_the_breaker_closed_again_is_not_counted_afterwards() -> None:
    clock = Clock()
    breaker = _breaker(clock)
    slow = _sent(breaker)
    _fail(breaker, 3)
    clock.advance(30)
    breaker.success(_sent(breaker))  # the trial closes the breaker
    breaker.failure(slow)
    _fail(breaker, 2)
    assert breaker.state == "closed", "two failures since the breaker closed, not three"
    _fail(breaker, 1)
    assert breaker.state == "open"


def test_a_success_does_not_clear_failures_of_calls_sent_after_it() -> None:
    breaker = _breaker(Clock())
    slow = _sent(breaker)
    _fail(breaker, 2)
    breaker.success(slow)  # sent before the two that failed
    _fail(breaker, 1)
    assert breaker.state == "open", "three failures in a row, in the order the calls were sent"


def test_a_failure_is_not_counted_once_a_call_sent_after_it_has_succeeded() -> None:
    breaker = _breaker(Clock())
    slow = _sent(breaker)
    breaker.success(_sent(breaker))
    breaker.failure(slow)
    _fail(breaker, 2)
    assert breaker.state == "closed"
    _fail(breaker, 1)
    assert breaker.state == "open"


def test_a_success_clears_only_the_failures_sent_before_it() -> None:
    breaker = _breaker(Clock())
    early = _sent(breaker)
    middle = _sent(breaker)
    late = _sent(breaker)
    breaker.failure(early)
    breaker.failure(late)
    breaker.success(middle)  # clears `early`, not `late`
    _fail(breaker, 1)
    assert breaker.state == "closed", "late and one more: two in a row"
    _fail(breaker, 1)
    assert breaker.state == "open"
