"""Token bucket that keeps EDGAR traffic at or under SEC's 10 requests per second.

`acquire` reserves the next free slot under a lock and sleeps outside it, so concurrent
callers queue in arrival order and never share a slot. With the default capacity of one
token, grants are spaced 1/rate apart and no one-second window holds more than `rate`.

`shared_bucket()` is the one bucket per process that every `EdgarClient` uses by default.
"""

import threading
import time
from collections.abc import Callable
from typing import Protocol

SEC_MAX_REQUESTS_PER_SECOND = 10


class RateLimiter(Protocol):
    """Blocks until the caller may send one request."""

    def acquire(self) -> None: ...


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

    def reserve(self) -> float:
        """Take one token now, possibly on credit; return how long to wait before using it."""
        with self._lock:
            now = self._clock()
            elapsed = max(0.0, now - self._updated)
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._updated = now
            self._tokens -= 1.0
            return 0.0 if self._tokens >= 0 else -self._tokens / self.rate

    def acquire(self) -> None:
        wait = self.reserve()
        if wait > 0:
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
