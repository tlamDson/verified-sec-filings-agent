"""Circuit breaker for one provider: stop calling it while it fails, then probe with one call.

closed: calls pass; `failure_threshold` failures in a row open it.
open: calls are refused until the wait is over.
half_open: one trial call passes; its success closes the breaker, its failure opens it again.
State is per process: each API replica learns a provider is down from its own calls.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

BreakerState = Literal["closed", "open", "half_open"]


@dataclass(frozen=True)
class BreakerConfig:
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0
    max_open_seconds: float = 3600.0
    """The longest a provider's own Retry-After can keep the breaker open."""

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("breaker: failure_threshold must be at least 1")
        if not 0 < self.cooldown_seconds <= self.max_open_seconds:
            raise ValueError("breaker: need 0 < cooldown_seconds <= max_open_seconds")


class CircuitBreaker:
    def __init__(self, config: BreakerConfig, clock: Callable[[], float]) -> None:
        self._config = config
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._open_until: float | None = None  # None: closed
        self._trial_out = False

    @property
    def state(self) -> BreakerState:
        with self._lock:
            return self._state()

    def acquire(self) -> bool:
        """Whether a call may go out now. Every True is followed by exactly one of
        `success`, `failure`, `trip` or `release`."""
        with self._lock:
            state = self._state()
            if state == "closed":
                return True
            if state == "open" or self._trial_out:
                return False
            self._trial_out = True
            return True

    def success(self) -> None:
        with self._lock:
            self._failures = 0
            self._open_until = None
            self._trial_out = False

    def failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._open_until is not None or self._failures >= self._config.failure_threshold:
                self._open(self._config.cooldown_seconds)

    def trip(self, seconds: float | None = None) -> None:
        """Open now, for `seconds` (at most `max_open_seconds`) or the cooldown."""
        wait = self._config.cooldown_seconds if seconds is None else seconds
        wait = min(max(wait, 0.0), self._config.max_open_seconds)
        with self._lock:
            self._open(wait)

    def release(self) -> None:
        """The call `acquire` allowed was not made, or says nothing about the provider."""
        with self._lock:
            self._trial_out = False

    def _open(self, seconds: float) -> None:
        self._open_until = self._clock() + seconds
        self._failures = 0
        self._trial_out = False

    def _state(self) -> BreakerState:
        if self._open_until is None:
            return "closed"
        return "open" if self._clock() < self._open_until else "half_open"
