"""Circuit breaker for one provider: stop calling it while it fails, then probe with one call.

closed: calls pass; `failure_threshold` failures in a row open it.
open: calls are refused until the wait is over.
half_open: one trial call passes; its success closes the breaker, its failure opens it again.

Calls overlap, so outcomes arrive in another order than the calls were sent. `acquire`
numbers each call (`Permit`), and an outcome is weighed by that number:
- A success or failure of a call sent before the breaker last opened changes nothing: it
  cannot close the breaker, restart its wait, or decide the trial that is out.
- While closed, "in a row" is in the order sent: a success clears only the failures of
  calls sent before it, and a failure is not counted once a later call has succeeded.
- A 429 (`trip`) is the provider's own word, valid from when it arrives, whichever call it
  answers: it opens the breaker, or lengthens a wait already running. No outcome shortens
  a wait.

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


@dataclass(frozen=True)
class Permit:
    """Leave to send one call. `sent` is its place in the order calls were let through."""

    sent: int


class CircuitBreaker:
    def __init__(self, config: BreakerConfig, clock: Callable[[], float]) -> None:
        self._config = config
        self._clock = clock
        self._lock = threading.Lock()
        self._sent = 0  # permits given so far
        self._stale_through = 0  # calls sent up to here predate the last time it opened
        self._newest_success = 0
        self._failed: set[int] = set()  # failures in a row while closed, by `Permit.sent`
        self._open_until: float | None = None  # None: closed
        self._trial: int | None = None  # the trial call that is out, by `Permit.sent`

    @property
    def state(self) -> BreakerState:
        with self._lock:
            return self._state()

    def acquire(self) -> Permit | None:
        """Leave to send a call now, or None. Every permit is given back to exactly one of
        `success`, `failure`, `trip` or `release`."""
        with self._lock:
            state = self._state()
            if state == "open" or (state == "half_open" and self._trial is not None):
                return None
            self._sent += 1
            if state == "half_open":
                self._trial = self._sent
            return Permit(self._sent)

    def success(self, permit: Permit) -> None:
        with self._lock:
            if self._is_stale(permit):
                return
            self._newest_success = max(self._newest_success, permit.sent)
            if self._open_until is None:
                self._failed = {sent for sent in self._failed if sent > permit.sent}
                return
            # not closed, and sent since it opened: this is the trial
            self._open_until = None
            self._trial = None

    def failure(self, permit: Permit) -> None:
        with self._lock:
            if self._is_stale(permit):
                return
            if self._open_until is not None:  # the trial failed
                self._open(self._config.cooldown_seconds)
                return
            if permit.sent < self._newest_success:
                return  # a call sent later has already succeeded
            self._failed.add(permit.sent)
            if len(self._failed) >= self._config.failure_threshold:
                self._open(self._config.cooldown_seconds)

    def trip(self, permit: Permit, seconds: float | None = None) -> None:
        """Open now, for `seconds` (at most `max_open_seconds`) or the cooldown; a wait
        already running is kept when it ends later. `permit` is the call that got the 429;
        when it was sent does not matter."""
        wait = self._config.cooldown_seconds if seconds is None else seconds
        wait = min(max(wait, 0.0), self._config.max_open_seconds)
        with self._lock:
            self._open(wait)

    def release(self, permit: Permit) -> None:
        """The call `acquire` allowed was not made, or says nothing about the provider."""
        with self._lock:
            if self._trial == permit.sent:
                self._trial = None

    def _is_stale(self, permit: Permit) -> bool:
        return permit.sent <= self._stale_through

    def _open(self, seconds: float) -> None:
        """Open for `seconds` from now, never ending a wait early. Every call in flight
        becomes stale, the trial included."""
        until = self._clock() + seconds
        self._open_until = until if self._open_until is None else max(self._open_until, until)
        self._stale_through = self._sent
        self._failed.clear()
        self._trial = None

    def _state(self) -> BreakerState:
        if self._open_until is None:
            return "closed"
        return "open" if self._clock() < self._open_until else "half_open"
