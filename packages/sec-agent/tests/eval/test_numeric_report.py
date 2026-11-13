"""The N1 report: accuracy with a Wilson interval, errors by kind, McNemar between systems."""

import datetime as dt

import pytest
from eval_data import number_question, peer_question

from sec_agent.eval.numeric.report import numeric_report
from sec_agent.eval.numeric.runner import AnswerRecord
from sec_agent.eval.stats.wilson import wilson_interval
from sec_agent.golden.gnum.models import NumQuestion

T0 = dt.datetime(2026, 11, 13, tzinfo=dt.UTC)
REVENUE = number_question("revenue", "100")
COGS = number_question("cost_of_revenue", "40")
MARGIN = number_question("gross_margin", "60", unit="percent", qtype="ratio")
PEER = peer_question("revenue")
QUESTIONS = [REVENUE, COGS, MARGIN, PEER]

RIGHT = (
    '{{"answer": "number", "value": {v}, "unit": "{u}",'
    ' "fiscal_year": 2024, "fiscal_period": "FY"}}'
)


def _record(
    q: NumQuestion, system: str, output: str, *, at: int = 0, model: str = "m"
) -> AnswerRecord:
    return AnswerRecord(
        qid=q.id,
        system=system,
        model=model,
        prompt_sha256="0" * 64,
        output=output,
        answered_at=T0 + dt.timedelta(minutes=at),
    )


B0 = [
    _record(REVENUE, "b0", RIGHT.format(v=100, u="USD")),
    _record(COGS, "b0", RIGHT.format(v=50, u="USD")),
    _record(MARGIN, "b0", "I think about 60 percent."),
    _record(PEER, "b0", '{"answer": "company", "ticker": "SIMW"}'),
]
B1 = [
    _record(REVENUE, "b1", RIGHT.format(v=100, u="USD")),
    _record(COGS, "b1", RIGHT.format(v=40, u="USD")),
    _record(MARGIN, "b1", RIGHT.format(v=60.05, u="percent")),
    _record(PEER, "b1", '{"answer": "company", "ticker": "SIMB"}'),
]


def test_accuracy_with_wilson_interval_and_errors() -> None:
    report = numeric_report(QUESTIONS, {"b0": B0, "b1": B1})
    assert (report.questions, report.scored, report.index_version) == (4, 4, "v-test")
    b0, b1 = report.systems
    assert (b0.system, b0.correct, b0.n, b0.accuracy) == ("b0", 1, 4, 0.25)
    assert b0.interval == wilson_interval(1, 4)
    assert b0.errors == {"wrong_value": 1, "unparsed": 1, "wrong_company": 1}
    assert b0.by_qtype == {"value": (1, 2), "ratio": (0, 1), "peer_comparison": (0, 1)}
    assert (b1.correct, b1.errors, b1.models) == (4, {}, ("m",))


def test_mcnemar_compares_each_later_system_with_each_earlier_one() -> None:
    report = numeric_report(QUESTIONS, {"b0": B0, "b1": B1})
    (comparison,) = report.comparisons
    assert (comparison.system, comparison.other) == ("b1", "b0")
    assert (comparison.result.a_only, comparison.result.b_only) == (3, 0)
    assert comparison.result.p_value == pytest.approx(0.25)


def test_only_questions_every_system_answered_are_scored() -> None:
    report = numeric_report(QUESTIONS, {"b0": B0[:3], "b1": B1})
    assert (report.questions, report.scored) == (4, 3)
    assert report.missing == {"b0": 1, "b1": 0}
    assert [s.n for s in report.systems] == [3, 3]


def test_two_answers_to_one_question_are_refused_not_guessed() -> None:
    fixed = _record(COGS, "b0", RIGHT.format(v=40, u="USD"), at=5)
    with pytest.raises(ValueError, match="two answers"):
        numeric_report(QUESTIONS, {"b0": [*B0, fixed]})


def test_results_mixing_models_are_refused() -> None:
    other = _record(COGS, "b0", RIGHT.format(v=40, u="USD"), model="m2")
    records = [r for r in B0 if r.qid != COGS.id] + [other]
    with pytest.raises(ValueError, match="mix models"):
        numeric_report(QUESTIONS, {"b0": records})


def test_answers_to_questions_outside_the_set_are_ignored() -> None:
    other = number_question("other", "1")
    report = numeric_report([REVENUE], {"b0": [*B0, _record(other, "b0", "x")]})
    assert (report.scored, report.systems[0].correct) == (1, 1)


def test_report_refuses_records_of_the_wrong_system_or_nothing_to_score() -> None:
    with pytest.raises(ValueError, match="b1"):
        numeric_report(QUESTIONS, {"b0": B1})
    with pytest.raises(ValueError, match="no question"):
        numeric_report(QUESTIONS, {"b0": []})
