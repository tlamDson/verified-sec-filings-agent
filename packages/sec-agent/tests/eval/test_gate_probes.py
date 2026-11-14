"""N1 probes: trap replies built from G-num answers, each with the grade it must get."""

from pathlib import Path

from sec_agent.eval.gate.probes import build_probes, probe_scores
from sec_agent.eval.numeric.grade import grade
from sec_agent.eval.numeric.reply import parse_reply
from sec_agent.golden.gnum.models import NumQuestion
from sec_agent.golden.jsonl import read_jsonl

REPO = Path(__file__).resolve().parents[4]


def _questions() -> list[NumQuestion]:
    return [
        q for q in read_jsonl(REPO / "data/golden/g_num.jsonl", NumQuestion) if q.split == "test"
    ]


def test_every_probe_gets_its_expected_grade_today() -> None:
    questions = {q.id: q for q in _questions()}
    probes = build_probes(list(questions.values()))
    assert len(probes) >= 100
    for p in probes:
        graded = grade(questions[p.qid], parse_reply(p.output))
        assert (graded.error or "correct") == p.expect, p


def test_probes_cover_the_edge_cases() -> None:
    cases = {p.case for p in build_probes(_questions())}
    assert cases >= {
        "exact",
        "rounded",
        "off_value",
        "other_period",
        "other_unit",
        "no_period",
        "draft_then_final",
        "right_peer",
        "wrong_peer",
    }


def test_probe_scores_are_one_per_case_and_all_pass() -> None:
    questions = _questions()
    scores = probe_scores(questions, build_probes(questions))
    assert scores
    assert all(share == 1.0 for share, _ in scores.values())
