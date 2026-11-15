"""Per-provider quota: requests per minute and per day, tokens per day.

A call is counted before it is made: `reserve` counts the request and holds the call's
token bound against the day, and `settle` replaces that hold with what the call used.
Calls in flight therefore cannot add up to more than a limit.

Windows are fixed UTC minutes and days. A free provider's own window may start elsewhere;
when the count here is still open and the provider says 429, the router's breaker waits.
`MemoryQuotaStore` counts for one process; `quota_postgres` shares one count across replicas.
"""

import datetime as dt
import threading
from typing import NamedTuple, Protocol

from pydantic import BaseModel, ConfigDict, PositiveInt


class QuotaLimits(BaseModel):
    """What a provider allows; None is no limit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requests_per_minute: PositiveInt | None = None
    requests_per_day: PositiveInt | None = None
    tokens_per_day: PositiveInt | None = None


class QuotaUsage(NamedTuple):
    minute_requests: int
    day_requests: int
    day_tokens: int
    """Tokens used by finished calls plus tokens held by calls still running."""


class QuotaStore(Protocol):
    def reserve(self, provider: str, limits: QuotaLimits, at: dt.datetime, tokens: int = 0) -> bool:
        """Count one request at `at` and hold `tokens` of its day, if every limit allows
        both; False, with nothing counted or held, if not."""
        ...

    def settle(self, provider: str, at: dt.datetime, *, held: int, used: int) -> None:
        """Replace the `held` tokens of a call reserved at `at` with the `used` it spent.

        `at` is the time the call was reserved, so a call that runs past midnight is
        settled on the day that holds it.
        """
        ...

    def usage(self, provider: str, at: dt.datetime) -> QuotaUsage:
        """The counts of the minute and the day `at` falls in."""
        ...


def minute_window(at: dt.datetime) -> dt.datetime:
    """The start of the UTC minute `at` falls in."""
    return _utc(at).replace(second=0, microsecond=0)


def day_window(at: dt.datetime) -> dt.datetime:
    """The start of the UTC day `at` falls in."""
    return _utc(at).replace(hour=0, minute=0, second=0, microsecond=0)


def allows(limits: QuotaLimits, used: QuotaUsage, tokens: int = 0) -> bool:
    """Whether one more request holding `tokens` fits under every limit.

    A day whose tokens are spent takes no call, even one that holds nothing.
    """
    return (
        _fits(used.minute_requests + 1, limits.requests_per_minute)
        and _fits(used.day_requests + 1, limits.requests_per_day)
        and _fits(used.day_tokens + max(tokens, 1), limits.tokens_per_day)
    )


_Key = tuple[str, dt.datetime]


class MemoryQuotaStore:
    """Counts in this process only: tests, a CLI run, a single replica."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._minute_requests: dict[_Key, int] = {}
        self._day_requests: dict[_Key, int] = {}
        self._day_tokens: dict[_Key, int] = {}

    def reserve(self, provider: str, limits: QuotaLimits, at: dt.datetime, tokens: int = 0) -> bool:
        minute, day = (provider, minute_window(at)), (provider, day_window(at))
        hold = max(0, tokens)
        with self._lock:
            if not allows(limits, self._usage(minute, day), hold):
                return False
            for key in [k for k in self._minute_requests if k[0] == provider and k != minute]:
                del self._minute_requests[key]
            self._minute_requests[minute] = self._minute_requests.get(minute, 0) + 1
            self._day_requests[day] = self._day_requests.get(day, 0) + 1
            self._day_tokens[day] = self._day_tokens.get(day, 0) + hold
            return True

    def settle(self, provider: str, at: dt.datetime, *, held: int, used: int) -> None:
        day = (provider, day_window(at))
        with self._lock:
            self._day_tokens[day] = max(0, self._day_tokens.get(day, 0) + settlement(held, used))

    def usage(self, provider: str, at: dt.datetime) -> QuotaUsage:
        with self._lock:
            return self._usage((provider, minute_window(at)), (provider, day_window(at)))

    def _usage(self, minute: _Key, day: _Key) -> QuotaUsage:
        return QuotaUsage(
            self._minute_requests.get(minute, 0),
            self._day_requests.get(day, 0),
            self._day_tokens.get(day, 0),
        )


def settlement(held: int, used: int) -> int:
    """What settling a call adds to the day's tokens: negative when it used less than held."""
    return max(0, used) - max(0, held)


def _fits(total: int, limit: int | None) -> bool:
    return limit is None or total <= limit


def _utc(at: dt.datetime) -> dt.datetime:
    if at.utcoffset() is None:
        raise ValueError("a quota time needs a time zone")
    return at.astimezone(dt.UTC)
