"""Reranker latency as runs.csv rows: p50 and p95 per call, nearest-rank percentiles."""

import datetime as dt
import math
import os
import platform
from collections.abc import Sequence

from sec_agent.runs import RunRow


def percentile(values: Sequence[float], p: float) -> float:
    """Nearest-rank percentile: the smallest value with at least p% of values at or below."""
    if not values:
        raise ValueError("percentile of no values")
    ordered = sorted(values)
    return ordered[max(1, math.ceil(p / 100 * len(ordered))) - 1]


def latency_rows(
    timings_ms: Sequence[float], *, system: str, config: str, date: dt.date, git_sha: str
) -> list[RunRow]:
    machine = f"{platform.processor() or platform.machine()}; {os.cpu_count()} logical CPUs"
    return [
        RunRow.model_validate(
            {
                "date": date,
                "git_sha": git_sha,
                "metric": f"L1_rerank_p{p}",
                "system": system,
                "split": "test",
                "cohort": "none",
                "n": len(timings_ms),
                "value": round(percentile(timings_ms, p), 3),
                "unit": "ms",
                "config": f"onnxruntime-cpu;{config}",
                "notes": f"one call scores one G-ret question's chunks; {machine}",
            }
        )
        for p in (50, 95)
    ]
