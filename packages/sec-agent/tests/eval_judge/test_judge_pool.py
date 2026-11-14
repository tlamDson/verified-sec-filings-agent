"""G-judge pool: each committed answer gets its stratum from the code graders."""

import pytest
from judge_kit import ASKED_ON, question, record, reply, scenario, transcript

from sec_agent.eval.agent.checks import Failure, FailureKind, ScenarioResult
from sec_agent.eval.judge.pool import (
    agent_candidates,
    agent_stratum,
    numeric_candidates,
    numeric_stratum,
)
from sec_agent.eval.numeric.grade import ErrorKind, Graded


@pytest.mark.parametrize(
    ("error", "stratum"),
    [
        (None, "correct"),
        ("wrong_value", "wrong_number"),
        ("wrong_unit", "wrong_number"),
        ("wrong_company", "wrong_number"),
        ("wrong_period", "wrong_period"),
        ("unparsed", None),
        ("not_found", None),
        ("wrong_kind", None),
    ],
)
def test_numeric_stratum(error: ErrorKind | None, stratum: str | None) -> None:
    assert numeric_stratum(Graded(correct=error is None, error=error)) == stratum


def result(*kinds: FailureKind) -> ScenarioResult:
    failures = tuple(Failure(kind=k, detail="") for k in kinds)
    return ScenarioResult(scenario_id="a1-001", passed=not kinds, failures=failures)


@pytest.mark.parametrize(
    ("kinds", "stratum"),
    [
        ((), "correct"),
        (("figure",), "wrong_number"),
        (("oracle",), "wrong_number"),
        (("figure", "unfaithful"), "wrong_number"),
        (("citation",), "citation"),
        (("unfaithful",), "citation"),
        (("citation", "outcome", "status"), "citation"),
        (("tool",), None),
        (("says",), None),
        (("non_answer",), None),
    ],
)
def test_agent_stratum(kinds: tuple[FailureKind, ...], stratum: str | None) -> None:
    assert agent_stratum(result(*kinds)) == stratum


def test_numeric_candidates_grade_each_record_and_skip_unscorable() -> None:
    right, late, off = question("revenue"), question("cash"), question("debt")
    records = [
        record(right, "b0", reply("1000")),
        record(late, "b0", reply("1000", fiscal_year=2023, period_end="2023-01-29")),
        record(off, "b1", reply("2000")),
        record(right, "b1", "I could not find it."),
        record(question("unknown"), "b1", reply("1000")),
    ]
    out = numeric_candidates([right, late, off], records)
    assert [(c.record_id, c.system, c.stratum) for c in out] == [
        (right.id, "b0", "correct"),
        (late.id, "b0", "wrong_period"),
        (off.id, "b1", "wrong_number"),
    ]
    first = out[0]
    assert first.origin == "numeric"
    assert first.turns == (right.question,)
    assert first.answer == records[0].output
    assert first.sources == ()
    assert first.grader_error is None
    assert out[2].grader_error == "wrong_value"


def test_agent_candidates_show_the_systems_evidence_never_the_oracle() -> None:
    plain, cited = scenario("a1-001", cite=False), scenario("a1-002", cite=True)
    text = "SIMW makes widgets. This is not investment advice."
    transcripts = [
        transcript("a1-001", "agent", text),
        transcript("a1-002", "rag", text),
        transcript("a1-999", "rag", text),
    ]
    out = agent_candidates([plain, cited], transcripts)
    assert [(c.record_id, c.system, c.stratum) for c in out] == [
        ("a1-001", "agent", "correct"),
        ("a1-002", "rag", "citation"),
    ]
    first = out[0]
    assert first.origin == "agent"
    assert first.turns == plain.turns
    assert first.asked_on == ASKED_ON
    assert first.answer == text
    assert [s.tool for s in first.sources] == ["search_filings"]
    assert all("gold" not in s.result for s in first.sources)
    assert out[1].grader_error == "citation"
