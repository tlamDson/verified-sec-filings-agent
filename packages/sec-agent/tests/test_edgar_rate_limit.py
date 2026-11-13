"""Token bucket: no window of one second ever holds more than 10 SEC requests."""

import random
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
        assert eleventh - first >= 1.0 - 1e-6


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


def _assert_at_most_ten_per_second(grants: list[float]) -> None:
    for first, eleventh in zip(grants, grants[10:], strict=False):
        assert eleventh - first >= 1.0 - 1e-6


def test_refused_attempt_takes_no_token(clock: FakeClock) -> None:
    bucket = _bucket(clock)
    assert bucket.try_acquire() == 0.0
    for _ in range(5):
        assert bucket.try_acquire() == pytest.approx(0.1)
    clock.now = 0.1
    assert bucket.try_acquire() == 0.0


def test_late_wakers_do_not_bunch_grants(clock: FakeClock) -> None:
    # Callers queued at the same instant all oversleep, then wake together: one is granted,
    # the rest wait again. A reserved-in-advance slot would let them all send at once.
    bucket = _bucket(clock)
    grants: list[float] = []
    for _ in range(10):
        assert bucket.try_acquire() == 0.0
        grants.append(clock.now)
        waiting = [bucket.try_acquire() for _ in range(9)]
        assert all(wait > 0 for wait in waiting)
        clock.now += 0.35
    assert grants == pytest.approx([0.35 * i for i in range(10)])


def test_random_wakeups_never_exceed_the_cap(clock: FakeClock) -> None:
    rng = random.Random(7)
    bucket = _bucket(clock)
    grants: list[float] = []
    for _ in range(3000):
        clock.now += rng.choice([0.0, 0.0, 0.01, 0.03, 0.07, 0.1, 0.25])
        if bucket.try_acquire() == 0.0:
            grants.append(clock.now)
    assert len(grants) > 100
    _assert_at_most_ten_per_second(grants)


def test_concurrent_oversleeping_threads_stay_under_the_cap(clock: FakeClock) -> None:
    lock = threading.Lock()
    grants: list[float] = []
    rng = random.Random(3)

    def oversleep(seconds: float) -> None:
        with lock:
            clock.now += seconds + rng.uniform(0.0, 0.3)

    def read_clock() -> float:
        with lock:
            return clock.now

    bucket = TokenBucket(rate=10.0, capacity=1.0, clock=read_clock, sleep=oversleep)

    def worker() -> None:
        for _ in range(10):
            granted_at = bucket.acquire()
            with lock:
                grants.append(granted_at)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(grants) == 80
    _assert_at_most_ten_per_second(sorted(grants))


def test_racing_threads_share_one_token(clock: FakeClock) -> None:
    bucket = _bucket(clock, capacity=3.0)
    results: list[float] = []
    lock = threading.Lock()
    barrier = threading.Barrier(16)

    def worker() -> None:
        barrier.wait()
        for _ in range(50):
            wait = bucket.try_acquire()
            with lock:
                results.append(wait)

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(0.0) == 3


@pytest.mark.parametrize(("rate", "capacity"), [(0.0, 1.0), (-1.0, 1.0), (10.0, 0.5)])
def test_rejects_invalid_settings(rate: float, capacity: float) -> None:
    with pytest.raises(ValueError, match=r"rate|capacity"):
        TokenBucket(rate=rate, capacity=capacity)


def test_shared_bucket_is_one_per_process() -> None:
    assert shared_bucket() is shared_bucket()
    assert shared_bucket().rate == SEC_MAX_REQUESTS_PER_SECOND
