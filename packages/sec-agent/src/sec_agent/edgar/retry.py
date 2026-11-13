"""Retry policy for EDGAR: which statuses to retry and how long to wait between attempts.

Delays use exponential backoff with full jitter: attempt n waits a uniform random time in
[0, min(max_delay, base_delay * 2**(n-1))], so workers that failed together do not retry
together. A server Retry-After is a floor on the wait.
"""

import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def is_retryable(status: int) -> bool:
    return status in RETRYABLE_STATUSES


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay: float = 0.5
    max_delay: float = 30.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be at least 1, got {self.max_attempts}")
        if not 0 < self.base_delay <= self.max_delay:
            raise ValueError("delays must satisfy 0 < base_delay <= max_delay")

    def delay(self, attempt: int, rng: random.Random, retry_after: float | None = None) -> float:
        """Seconds to wait after failed attempt number `attempt` (1-based)."""
        ceiling = min(self.max_delay, self.base_delay * 2 ** (attempt - 1))
        jittered = rng.uniform(0.0, ceiling)
        return jittered if retry_after is None else max(jittered, retry_after)


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    """Parse a Retry-After header (seconds or HTTP date); None when absent or invalid."""
    if value is None or not value.strip():
        return None
    text = value.strip()
    if text.isdigit():
        return float(text)
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    seconds = (when - (now or datetime.now(UTC))).total_seconds()
    return max(0.0, seconds) if math.isfinite(seconds) else None
