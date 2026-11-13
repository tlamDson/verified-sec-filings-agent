"""Token bucket that keeps EDGAR traffic at or under SEC's 10 requests per second.

A token is taken only at the moment the caller may send: `try_acquire` checks the bucket
under a lock and either takes a token now or says how long to wait, taking nothing. A caller
that sleeps and wakes late checks again, so late wakers cannot bunch up on slots reserved
earlier. With the default capacity of one token, grants are at least 1/rate apart on the
bucket's clock and no one-second window holds more than `rate` grants.

`shared_bucket()` is the one bucket per process that every `EdgarClient` uses by default.
"""

import threading
import time
from collections.abc import Callable
from typing import Protocol

SEC_MAX_REQUESTS_PER_SECOND = 10

# Float rounding can leave a refilled bucket a hair under one token; on a coarse clock the
# matching sub-nanosecond wait would never move time forward. Count that as a full token.
_TOKEN_EPSILON = 1e-9


class RateLimiter(Protocol):
    """Blocks until the caller may send one request; the return value is not used."""

    def acquire(self) -> object: ...


class TokenBucket:
    """Thread-safe token bucket with an injectable clock and sleep for tests."""

    def __init__(
        self,
        rate: float = SEC_MAX_REQUESTS_PER_SECOND,
        capacity: float = 1.0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate <= 0:
            raise ValueError(f"rate must be positive, got {rate}")
        if capacity < 1:
            raise ValueError(f"capacity must be at least 1 token, got {capacity}")
        self.rate = rate
        self.capacity = capacity
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._tokens = capacity
        self._updated = clock()

    def _attempt(self) -> tuple[float, float]:
        """Return (now, wait); a wait of 0.0 means one token was taken at `now`."""
        with self._lock:
            now = self._clock()
            elapsed = max(0.0, now - self._updated)
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._updated = now
            if self._tokens >= 1.0 - _TOKEN_EPSILON:
                self._tokens = max(0.0, self._tokens - 1.0)
                return now, 0.0
            return now, (1.0 - self._tokens) / self.rate

    def try_acquire(self) -> float:
        """Take a token now and return 0.0, or take nothing and return seconds to wait."""
        return self._attempt()[1]

    def acquire(self) -> float:
        """Block until a token is taken; return the clock reading at which it was taken."""
        while True:
            now, wait = self._attempt()
            if wait == 0.0:
                return now
            self._sleep(wait)


_shared: TokenBucket | None = None
_shared_lock = threading.Lock()


def shared_bucket() -> TokenBucket:
    """Return the process-wide bucket at SEC's limit, creating it on first use."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = TokenBucket()
        return _shared
