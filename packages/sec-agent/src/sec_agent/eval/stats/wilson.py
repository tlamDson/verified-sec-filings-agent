"""Wilson score interval for a proportion: stays inside [0, 1] and behaves at 0 and n."""

import math

from pydantic import BaseModel, ConfigDict

Z_95 = 1.959963984540054
"""The two-sided 95% normal quantile."""


class Interval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    low: float
    high: float


def wilson_interval(successes: int, n: int, z: float = Z_95) -> Interval:
    if n <= 0 or not 0 <= successes <= n:
        raise ValueError(f"need 0 <= successes <= n and n > 0, got successes={successes}, n={n}")
    p = successes / n
    z2 = z * z
    denominator = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denominator
    low = 0.0 if successes == 0 else max(0.0, center - half)
    high = 1.0 if successes == n else min(1.0, center + half)
    return Interval(low=low, high=high)
