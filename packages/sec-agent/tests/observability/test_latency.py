"""The L1 table: latency per step and tokens per question, computed from span records.

Timings and token counts below are simulated (hand-built spans), not measured.
"""

import datetime as dt
from dataclasses import astuple
from typing import Any

import pytest
from span_records import Trace, turn_trace

from sec_agent.observability.latency import (
    percentile,
    report_rows,
    trace_report,
)
from sec_agent.observability.span_file import SpanRecord


def test_percentile_interpolates_between_closest_ranks() -> None:
    assert percentile([5.0], 0.95) == 5.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert percentile([400.0, 100.0, 200.0], 0.95) == pytest.approx(380.0)
    assert percentile([1.0, 2.0], 0.0) == 1.0
    assert percentile([1.0, 2.0], 1.0) == 2.0


@pytest.mark.parametrize("q", [-0.1, 1.1])
def test_percentile_needs_q_between_zero_and_one(q: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        percentile([1.0], q)


def test_percentile_of_nothing_is_an_error() -> None:
    with pytest.raises(ValueError, match="no value"):
        percentile([], 0.5)


def _three_turns() -> list[SpanRecord]:
    return [
        *turn_trace(1, turn_ms=100, llm_ms=(60,), tool_ms=(10,), tokens=((100, 10),)),
        *turn_trace(2, turn_ms=200, llm_ms=(150,), tool_ms=(20,), tokens=((200, 20),)),
        *turn_trace(3, turn_ms=400, llm_ms=(300,), tool_ms=(50,), tokens=((300, 30),)),
    ]


def test_each_step_gets_its_p50_and_p95() -> None:
    report = trace_report(_three_turns())
    assert report.turns == 3
    assert [astuple(s) for s in report.steps] == [
        ("turn", 3, 0, 200.0, pytest.approx(380.0)),
        ("llm_call", 3, 0, 150.0, pytest.approx(285.0)),
        ("chat:a", 3, 0, 150.0, pytest.approx(285.0)),
        ("tool:get_fact", 3, 0, 20.0, pytest.approx(47.0)),
        ("agent_overhead", 3, 0, 30.0, pytest.approx(48.0)),
    ]


def test_tokens_per_question_sum_every_provider_call_of_the_turn() -> None:
    spans = [
        *turn_trace(1, turn_ms=100, llm_ms=(40, 40), tokens=((100, 10), (150, 20))),
        *turn_trace(2, turn_ms=100, llm_ms=(80,), tokens=((50, 5),)),
    ]
    report = trace_report(spans)
    assert [astuple(t) for t in report.tokens] == [
        ("input", 2, 150.0, 150.0, pytest.approx(240.0)),
        ("output", 2, 17.5, 17.5, pytest.approx(28.75)),
        ("total", 2, 167.5, 167.5, pytest.approx(268.75)),
    ]


def test_a_turn_without_a_model_answer_counts_zero_tokens() -> None:
    """A degraded turn used no tokens; it still is a question asked."""
    spans = [
        *turn_trace(1, turn_ms=50, llm_ms=(40,), tokens=((100, 10),)),
        *turn_trace(2, turn_ms=5, llm_ms=(4,)),
    ]
    (total,) = [t for t in trace_report(spans).tokens if t.kind == "total"]
    assert (total.n, total.mean) == (2, 55.0)


def test_failed_spans_are_counted_and_kept_in_the_latency() -> None:
    trace = Trace(1)
    turn = trace.span("turn", 0, 100)
    step = trace.span("llm_call", 0, 90, parent=turn)
    trace.span("chat", 0, 60, parent=step, status="error", **{"gen_ai.provider.name": "a"})
    trace.span("chat", 60, 30, parent=step, **{"gen_ai.provider.name": "b"})
    steps = {s.step: s for s in trace_report(trace.records).steps}
    assert (steps["chat:a"].n, steps["chat:a"].errors, steps["chat:a"].p50_ms) == (1, 1, 60.0)
    assert (steps["chat:b"].errors, steps["llm_call"].p50_ms) == (0, 90.0)


def test_provider_calls_outside_a_turn_count_as_calls_not_questions() -> None:
    """An eval baseline calls the router without the agent: latency yes, questions no."""
    trace = Trace(9)
    usage: dict[str, Any] = {"gen_ai.provider.name": "a", "gen_ai.usage.input_tokens": 9}
    trace.span("chat", 0, 70, **usage)
    report = trace_report([*turn_trace(1, turn_ms=10, llm_ms=(8,)), *trace.records])
    steps = {s.step: s for s in report.steps}
    assert steps["chat:a"].n == 2
    assert report.turns == 1
    assert {t.kind: t.n for t in report.tokens} == {"input": 1, "output": 1, "total": 1}


def test_spans_of_other_services_are_ignored() -> None:
    trace = Trace(1)
    trace.span("turn", 0, 10)
    other = trace.span("http", 0, 20)
    other.attributes.pop("sec_agent.step")
    assert [s.step for s in trace_report(trace.records).steps] == ["turn", "agent_overhead"]


def test_a_file_without_a_sec_agent_span_is_an_error() -> None:
    with pytest.raises(ValueError, match="no sec-agent span"):
        trace_report([])


def test_rows_for_runs_csv_name_the_step_and_the_statistic() -> None:
    report = trace_report(_three_turns())
    rows = report_rows(
        report,
        date=dt.date(2026, 11, 13),
        git_sha="abc1234",
        system="b2",
        split="dev",
        cohort="none",
        config="providers=local",
        notes="simulated model",
    )
    by_metric = {r.metric: r for r in rows}
    p95 = by_metric["L1.latency_p95.turn"]
    assert (p95.value, p95.unit, p95.n, p95.system, p95.split) == (380.0, "ms", 3, "b2", "dev")
    assert (p95.config, p95.notes, p95.cohort) == ("providers=local", "simulated model", "none")
    assert by_metric["L1.latency_p50.tool:get_fact"].value == 20.0
    tokens = by_metric["L1.tokens_per_question_mean.total"]
    assert (tokens.value, tokens.unit, tokens.n) == (220.0, "tokens", 3)
    assert "L1.tokens_per_question_p95.input" in by_metric
    assert len(rows) == 5 * 2 + 3 * 3
