"""Token bucket: no window of one second ever holds more than 10 SEC requests."""

import threading

import pytest

from sec_agent.edgar.rate_limit import SEC_MAX_REQUESTS_PER_SECOND, TokenBucket, shared_bucket


class FakeClock:
    """Monotonic clock that moves only when `sleep` is called."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def _bucket(clock: FakeClock, rate: float = 10.0, capacity: float = 1.0) -> TokenBucket:
    return TokenBucket(rate=rate, capacity=capacity, clock=clock, sleep=clock.sleep)


def test_sec_limit_is_ten_per_second() -> None:
    assert SEC_MAX_REQUESTS_PER_SECOND == 10
    assert TokenBucket().rate == 10


def test_first_request_does_not_wait(clock: FakeClock) -> None:
    _bucket(clock).acquire()
    assert sum(clock.sleeps) == 0


def test_any_one_second_window_holds_at_most_ten_grants(clock: FakeClock) -> None:
    bucket = _bucket(clock)
    grants: list[float] = []
    for _ in range(35):
        bucket.acquire()
        grants.append(clock.now)
    for first, eleventh in zip(grants, grants[10:], strict=False):
        assert eleventh - first >= 1.0 - 1e-9


def test_burst_capacity_is_respected(clock: FakeClock) -> None:
    bucket = _bucket(clock, rate=10.0, capacity=5.0)
    for _ in range(5):
        bucket.acquire()
    assert sum(clock.sleeps) == 0
    bucket.acquire()
    assert clock.sleeps[-1] == pytest.approx(0.1)


def test_idle_time_refills_only_up_to_capacity(clock: FakeClock) -> None:
    bucket = _bucket(clock)
    bucket.acquire()
    clock.now += 60.0
    waits: list[float] = []
    for _ in range(3):
        before = clock.now
        bucket.acquire()
        waits.append(clock.now - before)
    assert waits == pytest.approx([0.0, 0.1, 0.1])


def test_concurrent_callers_each_get_their_own_slot(clock: FakeClock) -> None:
    waits: list[float] = []
    lock = threading.Lock()

    def record(seconds: float) -> None:
        with lock:
            waits.append(seconds)

    # The clock stands still, so every grant must be reserved one slot after the last one.
    bucket = TokenBucket(rate=10.0, capacity=1.0, clock=clock, sleep=record)
    threads = [
        threading.Thread(target=lambda: [bucket.acquire() for _ in range(5)]) for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    slots = sorted(round(wait * 10) for wait in waits if wait > 0)
    assert len(waits) - len(slots) <= 1
    assert slots == list(range(40 - len(slots), 40))


@pytest.mark.parametrize(("rate", "capacity"), [(0.0, 1.0), (-1.0, 1.0), (10.0, 0.5)])
def test_rejects_invalid_settings(rate: float, capacity: float) -> None:
    with pytest.raises(ValueError, match=r"rate|capacity"):
        TokenBucket(rate=rate, capacity=capacity)


def test_shared_bucket_is_one_per_process() -> None:
    assert shared_bucket() is shared_bucket()
    assert shared_bucket().rate == SEC_MAX_REQUESTS_PER_SECOND
