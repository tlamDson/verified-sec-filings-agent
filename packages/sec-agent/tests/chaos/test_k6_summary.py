"""k6's summary export -> one runs.csv row per load number, labelled simulated."""

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from sec_agent.chaos.k6_summary import METRIC_NAMES, LoadSummary, load_rows, parse_k6_summary
from sec_agent.runs import RunRow

FIXTURE = Path(__file__).parent.parent / "fixtures" / "k6" / "summary.sim.json"


def _data() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text("utf-8"))


def test_parse_reads_the_custom_metrics() -> None:
    summary = parse_k6_summary(_data())
    assert summary == LoadSummary(
        max_vus=200,
        turns=400,
        turns_failed=4,
        resumes=100,
        resumes_failed=1,
        answered=350,
        degraded=46,
        turn_p50_ms=640.0,
        turn_p95_ms=2100.25,
    )


def test_metric_names_cover_what_the_parser_reads() -> None:
    assert set(METRIC_NAMES) == {
        "turn_failed",
        "resume_failed",
        "turn_ms",
        "turn_answered",
        "turn_degraded",
    }


def test_a_missing_metric_is_an_error_naming_it() -> None:
    data = _data()
    del data["metrics"]["resume_failed"]
    with pytest.raises(ValueError, match="resume_failed"):
        parse_k6_summary(data)


def test_a_run_with_no_turn_is_an_error() -> None:
    data = _data()
    data["metrics"]["turn_failed"] = {"passes": 0, "fails": 0, "value": 0}
    with pytest.raises(ValueError, match="no turn"):
        parse_k6_summary(data)


def test_rows_are_valid_simulated_and_carry_intervals() -> None:
    rows = load_rows(
        parse_k6_summary(_data()),
        date=dt.date(2026, 11, 13),
        git_sha="abc1234",
        system="api-x3+fake-llm",
        config="200 VU, kill api-2",
    )
    by_metric = {row.metric: row for row in rows}
    assert set(by_metric) == {
        "LOAD.turn_error_rate",
        "LOAD.resume_error_rate",
        "LOAD.degraded_share",
        "LOAD.turn_p50",
        "LOAD.turn_p95",
    }
    for row in rows:
        RunRow.model_validate(row.model_dump())
        assert row.cohort == "simulated"
        assert row.split == "none"
        assert row.system == "api-x3+fake-llm"
        assert "simulated" in row.notes
    errors = by_metric["LOAD.turn_error_rate"]
    assert (errors.n, errors.value, errors.unit) == (400, 0.01, "fraction")
    assert errors.ci_low is not None
    assert errors.ci_high is not None
    assert errors.ci_low < 0.01 < errors.ci_high
    assert by_metric["LOAD.resume_error_rate"].n == 100
    assert by_metric["LOAD.degraded_share"].value == pytest.approx(46 / 396)
    assert by_metric["LOAD.degraded_share"].n == 396
    p95 = by_metric["LOAD.turn_p95"]
    assert (p95.value, p95.unit, p95.n, p95.ci_low) == (2100.25, "ms", 400, None)
