"""J1: Cohen's kappa, TPR and TNR of a judge against the blind labels."""

import datetime as dt

import pytest

from sec_agent.eval.judge.models import KeyEntry, Label, LabelValue, Verdict, VerdictValue
from sec_agent.eval.judge.rows import judge_rows
from sec_agent.eval.judge.score import Pair, cohen_kappa, grader_verdicts, score_judge


def labels_and_verdicts(
    cells: dict[tuple[VerdictValue, VerdictValue], int],
) -> tuple[list[Label], list[Verdict]]:
    labels: list[Label] = []
    verdicts: list[Verdict] = []
    n = 0
    for (label, verdict), count in cells.items():
        for _ in range(count):
            labels.append(Label(id=f"gj-{n:012x}", label=label, rater="sim-rater"))
            verdicts.append(Verdict(id=f"gj-{n:012x}", verdict=verdict, judge="sim-judge"))
            n += 1
    return labels, verdicts


TABLE: dict[tuple[VerdictValue, VerdictValue], int] = {
    ("correct", "correct"): 20,
    ("correct", "incorrect"): 5,
    ("incorrect", "correct"): 10,
    ("incorrect", "incorrect"): 15,
}


def test_kappa_tpr_tnr_on_a_known_table() -> None:
    labels, verdicts = labels_and_verdicts(TABLE)
    score = score_judge(labels, verdicts, judge="sim-judge")
    assert score.n == 50
    assert score.agreement == pytest.approx(0.7)
    assert score.kappa == pytest.approx(0.4)
    assert score.tpr == pytest.approx(0.8)
    assert score.tnr == pytest.approx(0.6)
    assert score.tpr_interval is not None
    assert score.tpr_interval.low < 0.8 < score.tpr_interval.high


def test_kappa_is_undefined_when_both_sides_never_vary() -> None:
    agree: Pair = ("correct", "correct")
    disagree: Pair = ("incorrect", "incorrect")
    assert cohen_kappa([agree] * 4) is None
    assert cohen_kappa([agree, disagree]) == pytest.approx(1)


def test_unsure_labels_and_missing_verdicts_are_counted_not_scored() -> None:
    labels, verdicts = labels_and_verdicts(TABLE)
    labels.append(Label(id="gj-unsure000001", label="unsure", rater="sim-rater"))
    labels.append(Label(id="gj-noverdict001", label="correct", rater="sim-rater"))
    verdicts.append(Verdict(id="gj-unsure000001", verdict="correct", judge="sim-judge"))
    score = score_judge(labels, verdicts, judge="sim-judge")
    assert (score.n, score.unsure, score.missing) == (50, 1, 1)


def test_only_positives_leaves_tnr_undefined() -> None:
    labels, verdicts = labels_and_verdicts({("correct", "correct"): 3})
    score = score_judge(labels, verdicts, judge="sim-judge")
    assert (score.tpr, score.tnr, score.tnr_interval) == (1.0, None, None)


@pytest.mark.parametrize("problem", ["duplicate_label", "duplicate_verdict", "unknown_id"])
def test_bad_files_are_errors(problem: str) -> None:
    labels, verdicts = labels_and_verdicts(TABLE)
    if problem == "duplicate_label":
        labels.append(labels[0])
    elif problem == "duplicate_verdict":
        verdicts.append(verdicts[0])
    else:
        verdicts.append(Verdict(id="gj-notlabelled1", verdict="correct", judge="sim-judge"))
    with pytest.raises(ValueError, match="gj-"):
        score_judge(labels, verdicts, judge="sim-judge")


def test_verdicts_of_another_judge_are_an_error() -> None:
    labels, verdicts = labels_and_verdicts(TABLE)
    with pytest.raises(ValueError, match="other-judge"):
        score_judge(labels, verdicts, judge="other-judge")


def test_grader_verdicts_come_from_the_key() -> None:
    key = [
        KeyEntry(
            id="gj-000000000001",
            origin="agent",
            record_id="a1-001",
            system="rag",
            model="sim",
            stratum="citation",
            grader_error="citation",
            grader_verdict="incorrect",
        )
    ]
    assert grader_verdicts(key) == [
        Verdict(id="gj-000000000001", verdict="incorrect", judge="grader")
    ]


def test_rows_name_the_judge_and_the_labellers() -> None:
    labels, verdicts = labels_and_verdicts(TABLE)
    score = score_judge(labels, verdicts, judge="sim-judge")
    rows = judge_rows(
        [score],
        labelled_by="LLM raters, owner-checked",
        date=dt.date(2026, 11, 14),
        git_sha="abc1234",
    )
    assert [(r.metric, r.unit) for r in rows] == [
        ("J1_kappa", "kappa"),
        ("J1_tpr", "fraction"),
        ("J1_tnr", "fraction"),
    ]
    assert {r.system for r in rows} == {"sim-judge"}
    assert {(r.split, r.cohort, r.n) for r in rows} == {("test", "none", 50)}
    assert all("LLM raters, owner-checked" in r.notes for r in rows)
    assert rows[1].ci_low is not None
    assert rows[0].ci_low is None


def test_label_value_has_unsure() -> None:
    values: tuple[LabelValue, ...] = ("correct", "incorrect", "unsure")
    assert all(Label(id="gj-000000000001", label=v, rater="r").label == v for v in values)
