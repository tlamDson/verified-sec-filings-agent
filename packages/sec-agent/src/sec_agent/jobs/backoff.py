"""Retry delay for failed jobs: exponential growth, a cap, and full jitter."""

import random


def retry_delay(attempt: int, *, base: float, cap: float, rng: random.Random) -> float:
    """Seconds to wait before retry after `attempt` (1-based) failed.

    The ceiling is `base * 2**(attempt - 1)`, capped at `cap`; the delay is drawn uniformly
    from [0, ceiling] ("full jitter") so workers that fail together do not retry together.
    """
    if attempt < 1 or base <= 0 or cap < base:
        raise ValueError(f"retry_delay needs attempt >= 1 and 0 < base <= cap, got {attempt=}")
    exponent = min(attempt - 1, 64)  # 2**64 * base is past any sane cap; avoids overflow
    ceiling = min(cap, base * 2.0**exponent)
    return ceiling * rng.random()
