"""Read k6's `--summary-export` JSON for the custom metrics `infra/load/chat.js` emits.

The script counts outcomes per turn, not per HTTP request: a turn fails when the stream
does not end with an `answer` event (a refused request, a dropped connection, an `error`
event). k6 writes a Rate as `passes` (true samples) and `fails` (false samples), a Trend as
percentiles, a Counter as `count`.
"""

import datetime as dt
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.chaos.rows import proportion_row
from sec_agent.runs import RunRow

TURN_FAILED = "turn_failed"
RESUME_FAILED = "resume_failed"
TURN_MS = "turn_ms"
TURN_ANSWERED = "turn_answered"
TURN_DEGRADED = "turn_degraded"
LOAD_NOTE = "simulated accounts against a simulated model (sec-agent chaos fake-llm)"
METRIC_NAMES: tuple[str, ...] = (TURN_FAILED, RESUME_FAILED, TURN_MS, TURN_ANSWERED, TURN_DEGRADED)


class LoadSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_vus: int = Field(ge=0)
    turns: int = Field(gt=0)
    turns_failed: int = Field(ge=0)
    resumes: int = Field(ge=0)
    """Second turns on a conversation that already had one."""
    resumes_failed: int = Field(ge=0)
    answered: int = Field(ge=0)
    degraded: int = Field(ge=0)
    turn_p50_ms: float = Field(ge=0)
    turn_p95_ms: float = Field(ge=0)

    @property
    def turns_completed(self) -> int:
        return self.turns - self.turns_failed


def parse_k6_summary(data: Mapping[str, Any]) -> LoadSummary:
    """Raise ValueError naming the metric when one is missing or has the wrong shape."""
    metrics: Mapping[str, Any] = data.get("metrics") or {}
    turns_failed, turns = _rate(metrics, TURN_FAILED)
    if turns == 0:
        raise ValueError("the run recorded no turn")
    resumes_failed, resumes = _rate(metrics, RESUME_FAILED)
    trend = _metric(metrics, TURN_MS)
    return LoadSummary(
        max_vus=_max_vus(metrics),
        turns=turns,
        turns_failed=turns_failed,
        resumes=resumes,
        resumes_failed=resumes_failed,
        answered=_count(metrics, TURN_ANSWERED),
        degraded=_count(metrics, TURN_DEGRADED),
        turn_p50_ms=_number(trend, "med", TURN_MS),
        turn_p95_ms=_number(trend, "p(95)", TURN_MS),
    )


def load_rows(
    summary: LoadSummary, *, date: dt.date, git_sha: str, system: str, config: str = ""
) -> list[RunRow]:
    common: dict[str, object] = {
        "date": date,
        "git_sha": git_sha,
        "system": system,
        "split": "none",
        "cohort": "simulated",
        "config": f"{config}; max {summary.max_vus} VU".lstrip("; "),
        "notes": LOAD_NOTE,
    }
    rows = [
        proportion_row("LOAD.turn_error_rate", summary.turns_failed, summary.turns, common),
        _timing("LOAD.turn_p50", summary.turn_p50_ms, summary.turns, common),
        _timing("LOAD.turn_p95", summary.turn_p95_ms, summary.turns, common),
    ]
    if summary.resumes:
        rows.append(
            proportion_row(
                "LOAD.resume_error_rate", summary.resumes_failed, summary.resumes, common
            )
        )
    if summary.turns_completed:
        rows.append(
            proportion_row("LOAD.degraded_share", summary.degraded, summary.turns_completed, common)
        )
    return rows


def _timing(metric: str, value: float, n: int, common: dict[str, object]) -> RunRow:
    return RunRow.model_validate({**common, "metric": metric, "n": n, "value": value, "unit": "ms"})


def _metric(metrics: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = metrics.get(name)
    if not isinstance(value, Mapping):
        raise ValueError(f"k6 summary has no metric {name!r}")
    return value  # pyright: ignore[reportUnknownVariableType]


def _number(metric: Mapping[str, Any], field: str, name: str) -> float:
    value = metric.get(field)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"k6 metric {name!r} has no number {field!r}")
    return float(value)


def _rate(metrics: Mapping[str, Any], name: str) -> tuple[int, int]:
    """(true samples, all samples) of a Rate metric."""
    metric = _metric(metrics, name)
    true = int(_number(metric, "passes", name))
    false = int(_number(metric, "fails", name))
    return true, true + false


def _max_vus(metrics: Mapping[str, Any]) -> int:
    """k6 writes the Gauge `vus_max` with `value`, `min` and `max`; absent means unknown, 0."""
    if metrics.get("vus_max") is None:
        return 0
    gauge = _metric(metrics, "vus_max")
    return int(_number(gauge, "max" if "max" in gauge else "value", "vus_max"))


def _count(metrics: Mapping[str, Any], name: str) -> int:
    """A Counter k6 never added to is absent from the export: that is zero."""
    metric = metrics.get(name)
    if metric is None:
        return 0
    return int(_number(_metric(metrics, name), "count", name))
