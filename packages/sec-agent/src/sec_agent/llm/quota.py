"""Per-provider quota: requests per minute and per day, tokens per day.

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


class QuotaStore(Protocol):
    def reserve(self, provider: str, limits: QuotaLimits, at: dt.datetime) -> bool:
        """Count one request at `at` if every limit allows it; False (and no count) if not."""
        ...

    def add_tokens(self, provider: str, tokens: int, at: dt.datetime) -> None:
        """Add the tokens a finished call used to the day of `at`."""
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


def allows(limits: QuotaLimits, used: QuotaUsage) -> bool:
    """Whether one more request fits under every limit."""
    return (
        _under(used.minute_requests, limits.requests_per_minute)
        and _under(used.day_requests, limits.requests_per_day)
        and _under(used.day_tokens, limits.tokens_per_day)
    )


_Key = tuple[str, dt.datetime]


class MemoryQuotaStore:
    """Counts in this process only: tests, a CLI run, a single replica."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._minute_requests: dict[_Key, int] = {}
        self._day_requests: dict[_Key, int] = {}
        self._day_tokens: dict[_Key, int] = {}

    def reserve(self, provider: str, limits: QuotaLimits, at: dt.datetime) -> bool:
        minute, day = (provider, minute_window(at)), (provider, day_window(at))
        with self._lock:
            if not allows(limits, self._usage(minute, day)):
                return False
            for key in [k for k in self._minute_requests if k[0] == provider and k != minute]:
                del self._minute_requests[key]
            self._minute_requests[minute] = self._minute_requests.get(minute, 0) + 1
            self._day_requests[day] = self._day_requests.get(day, 0) + 1
            return True

    def add_tokens(self, provider: str, tokens: int, at: dt.datetime) -> None:
        day = (provider, day_window(at))
        with self._lock:
            self._day_tokens[day] = self._day_tokens.get(day, 0) + max(0, tokens)

    def usage(self, provider: str, at: dt.datetime) -> QuotaUsage:
        with self._lock:
            return self._usage((provider, minute_window(at)), (provider, day_window(at)))

    def _usage(self, minute: _Key, day: _Key) -> QuotaUsage:
        return QuotaUsage(
            self._minute_requests.get(minute, 0),
            self._day_requests.get(day, 0),
            self._day_tokens.get(day, 0),
        )


def _under(used: int, limit: int | None) -> bool:
    return limit is None or used < limit


def _utc(at: dt.datetime) -> dt.datetime:
    if at.utcoffset() is None:
        raise ValueError("a quota time needs a time zone")
    return at.astimezone(dt.UTC)
