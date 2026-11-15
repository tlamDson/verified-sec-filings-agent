"""L1 from spans: p50 and p95 latency per step, and tokens per question.

Steps: `turn` (a whole question, end to end), `llm_call` (one model call, failover
included), `chat:<provider>` (one call to that provider), `tool:<name>`, and
`agent_overhead` (a turn's time outside its model calls and tools: checkpoints, graph).
Failed spans are counted (`errors`) and kept in the latency: a timeout is time a user
waited. Tokens per question add up every provider call under a turn, as the providers
reported them; a provider call outside any turn (an eval baseline) counts toward its
step's latency but asks no question.

Percentiles interpolate linearly between the closest ranks (Hyndman and Fan type 7, the
default of numpy and R).
"""

import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sec_agent.observability import conventions as c
from sec_agent.observability.span_file import SpanRecord
from sec_agent.runs import Cohort, RunRow, Split

TokenKind = Literal["input", "output", "total"]
TOKEN_KINDS: tuple[TokenKind, ...] = ("input", "output", "total")
OVERHEAD = "agent_overhead"


@dataclass(frozen=True)
class StepLatency:
    step: str
    n: int
    errors: int
    p50_ms: float
    p95_ms: float


@dataclass(frozen=True)
class TokenStats:
    kind: TokenKind
    n: int
    """Questions (turns)."""
    mean: float
    p50: float
    p95: float


@dataclass(frozen=True)
class TraceReport:
    turns: int
    steps: tuple[StepLatency, ...]
    tokens: tuple[TokenStats, ...]
    """Empty when the spans hold no turn."""


def percentile(values: Sequence[float], q: float) -> float:
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be between 0 and 1")
    if not values:
        raise ValueError("no value to take a percentile of")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * q
    low = math.floor(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (rank - low) * (ordered[high] - ordered[low])


def trace_report(spans: Sequence[SpanRecord]) -> TraceReport:
    ours = [s for s in spans if isinstance(s.attributes.get(c.STEP), str)]
    if not ours:
        raise ValueError("no sec-agent span in the spans given")
    groups: dict[str, list[SpanRecord]] = {}
    for span in ours:
        key = _step_key(span)
        if key is not None:
            groups.setdefault(key, []).append(span)
    turns = groups.get("turn", [])
    steps = [_latency(key, groups[key]) for key in _ordered(groups)]
    if turns:
        overheads = [_overhead(turn, ours) for turn in turns]
        steps.append(_stats_ms(OVERHEAD, overheads, errors=0))
    return TraceReport(turns=len(turns), steps=tuple(steps), tokens=_tokens(turns, ours))


def report_rows(
    report: TraceReport,
    *,
    date: dt.date,
    git_sha: str,
    system: str,
    split: Split,
    cohort: Cohort,
    index_version: str = "",
    config: str = "",
    notes: str = "",
) -> list[RunRow]:
    """The report as runs.csv rows: `L1.latency_p50.<step>` and `L1.latency_p95.<step>`
    in ms, and `L1.tokens_per_question_{mean,p50,p95}.<kind>` in tokens."""

    def row(metric: str, n: int, value: float, unit: str) -> RunRow:
        return RunRow(
            date=date,
            git_sha=git_sha,
            metric=metric,
            system=system,
            split=split,
            cohort=cohort,
            n=n,
            value=round(value, 3),
            unit=unit,
            index_version=index_version,
            config=config,
            notes=notes,
        )

    rows: list[RunRow] = []
    for step in report.steps:
        rows.append(row(f"L1.latency_p50.{step.step}", step.n, step.p50_ms, "ms"))
        rows.append(row(f"L1.latency_p95.{step.step}", step.n, step.p95_ms, "ms"))
    for stats in report.tokens:
        for name, value in (("mean", stats.mean), ("p50", stats.p50), ("p95", stats.p95)):
            metric = f"L1.tokens_per_question_{name}.{stats.kind}"
            rows.append(row(metric, stats.n, value, "tokens"))
    return rows


def _step_key(span: SpanRecord) -> str | None:
    step = span.attributes.get(c.STEP)
    if step in ("turn", "llm_call"):
        return str(step)
    if step == "chat":
        return f"chat:{span.attributes.get(c.PROVIDER, 'unknown')}"
    if step == "tool":
        return f"tool:{span.attributes.get(c.TOOL_NAME, 'unknown')}"
    return None


def _ordered(groups: dict[str, list[SpanRecord]]) -> list[str]:
    fixed = [k for k in ("turn", "llm_call") if k in groups]
    chats = sorted(k for k in groups if k.startswith("chat:"))
    tools = sorted(k for k in groups if k.startswith("tool:"))
    return [*fixed, *chats, *tools]


def _latency(step: str, spans: list[SpanRecord]) -> StepLatency:
    errors = sum(1 for s in spans if s.status == "error")
    return _stats_ms(step, [s.duration_ms for s in spans], errors=errors)


def _stats_ms(step: str, values: list[float], *, errors: int) -> StepLatency:
    return StepLatency(step, len(values), errors, percentile(values, 0.5), percentile(values, 0.95))


def _overhead(turn: SpanRecord, spans: list[SpanRecord]) -> float:
    inside = sum(
        s.duration_ms
        for s in spans
        if s.trace_id == turn.trace_id
        and s.parent_id == turn.span_id
        and s.attributes.get(c.STEP) in ("llm_call", "tool")
    )
    return max(0.0, turn.duration_ms - inside)


def _tokens(turns: list[SpanRecord], spans: list[SpanRecord]) -> tuple[TokenStats, ...]:
    if not turns:
        return ()
    by_id = {(s.trace_id, s.span_id): s for s in spans}
    sums = {(t.trace_id, t.span_id): [0, 0, 0] for t in turns}
    for span in spans:
        if span.attributes.get(c.STEP) != "chat":
            continue
        turn = _turn_of(span, by_id)
        if turn is None or (turn.trace_id, turn.span_id) not in sums:
            continue
        counts = sums[(turn.trace_id, turn.span_id)]
        sent, received = _count(span, c.INPUT_TOKENS), _count(span, c.OUTPUT_TOKENS)
        counts[0] += sent
        counts[1] += received
        counts[2] += max(_count(span, c.OI_TOTAL_TOKENS), sent + received)
    per_turn = list(sums.values())
    return tuple(
        _token_stats(kind, [float(counts[index]) for counts in per_turn])
        for index, kind in enumerate(TOKEN_KINDS)
    )


def _turn_of(span: SpanRecord, by_id: dict[tuple[str, str], SpanRecord]) -> SpanRecord | None:
    seen: set[str] = set()
    current = span
    while current.parent_id is not None and current.parent_id not in seen:
        seen.add(current.parent_id)
        parent = by_id.get((current.trace_id, current.parent_id))
        if parent is None:
            return None
        if parent.attributes.get(c.STEP) == "turn":
            return parent
        current = parent
    return None


def _count(span: SpanRecord, key: str) -> int:
    value = span.attributes.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _token_stats(kind: TokenKind, values: list[float]) -> TokenStats:
    return TokenStats(
        kind,
        len(values),
        sum(values) / len(values),
        percentile(values, 0.5),
        percentile(values, 0.95),
    )
