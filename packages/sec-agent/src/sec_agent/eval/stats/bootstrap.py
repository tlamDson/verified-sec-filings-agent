"""Bootstrap by company (cluster bootstrap): resample companies, not questions.

Questions about one company are not independent (same filings, same index quality), and
the test split has only 10 companies, so the interval must come from resampling companies.
Each resample draws as many companies as there are, with replacement, and takes the mean
over all their questions (each question weighs the same). The interval is the percentile
interval of those means. A paired comparison does the same on per-question differences
a - b; its two-sided p value is 2 * (1 + resamples on the far side of 0) / (1 + resamples),
capped at 1. A seeded `random.Random` makes every number reproducible.
"""

import math
import random
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_RESAMPLES = 10_000


class BootstrapResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    estimate: float
    low: float
    high: float
    n: int = Field(ge=1)
    """Questions."""
    clusters: int = Field(ge=1)
    resamples: int = Field(ge=1)
    level: float


class PairedResult(BootstrapResult):
    p_value: float = Field(ge=0, le=1)


def bootstrap_mean(
    values: Mapping[str, Sequence[float]], *, resamples: int, seed: int, level: float = 0.95
) -> BootstrapResult:
    """Mean over every value, with a percentile interval from resampling the clusters."""
    clusters = _summaries(values)
    means = _resample(clusters, resamples, seed)
    low, high = _percentiles(means, level)
    return BootstrapResult(
        estimate=_mean(clusters),
        low=low,
        high=high,
        n=sum(count for _, count in clusters),
        clusters=len(clusters),
        resamples=resamples,
        level=level,
    )


def paired_bootstrap(
    a: Mapping[str, Sequence[float]],
    b: Mapping[str, Sequence[float]],
    *,
    resamples: int,
    seed: int,
    level: float = 0.95,
) -> PairedResult:
    """Mean of a - b over paired questions (same clusters, same order inside each)."""
    if set(a) != set(b) or any(len(a[key]) != len(b[key]) for key in a):
        raise ValueError("need paired values: the same clusters with the same questions")
    diffs = {key: [x - y for x, y in zip(a[key], b[key], strict=True)] for key in a}
    clusters = _summaries(diffs)
    means = _resample(clusters, resamples, seed)
    low, high = _percentiles(means, level)
    at_or_below = sum(1 for m in means if m <= 0)
    at_or_above = sum(1 for m in means if m >= 0)
    p_value = min(1.0, 2 * (1 + min(at_or_below, at_or_above)) / (1 + resamples))
    return PairedResult(
        estimate=_mean(clusters),
        low=low,
        high=high,
        n=sum(count for _, count in clusters),
        clusters=len(clusters),
        resamples=resamples,
        level=level,
        p_value=p_value,
    )


def _summaries(values: Mapping[str, Sequence[float]]) -> list[tuple[float, int]]:
    """(sum, count) per non-empty cluster, in key order so the seed fixes every draw."""
    clusters = [(math.fsum(values[key]), len(values[key])) for key in sorted(values)]
    clusters = [c for c in clusters if c[1] > 0]
    if not clusters:
        raise ValueError("no values to bootstrap")
    return clusters


def _mean(clusters: Sequence[tuple[float, int]]) -> float:
    return math.fsum(s for s, _ in clusters) / sum(c for _, c in clusters)


def _resample(clusters: Sequence[tuple[float, int]], resamples: int, seed: int) -> list[float]:
    if resamples < 1:
        raise ValueError(f"resamples must be at least 1, got {resamples}")
    rng = random.Random(seed)
    k = len(clusters)
    return sorted(_mean(rng.choices(clusters, k=k)) for _ in range(resamples))


def _percentiles(sorted_means: Sequence[float], level: float) -> tuple[float, float]:
    if not 0 < level < 1:
        raise ValueError(f"level must be between 0 and 1, got {level}")
    count = len(sorted_means)
    low_index = math.floor((1 - level) / 2 * count)
    high_index = max(low_index, math.ceil((1 + level) / 2 * count) - 1)
    return sorted_means[low_index], sorted_means[min(high_index, count - 1)]
