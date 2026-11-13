"""Retrieval baselines without a database, TREC run text, and the R1 report."""

import datetime as dt

import pytest

from sec_agent.eval.retrieval.rankers import collect_runs, oracle_ranking, random_ranking
from sec_agent.eval.retrieval.report import retrieval_report
from sec_agent.golden.gret.models import ChunkRef, RetQuestion, RunHit
from sec_agent.golden.gret.trec import parse_run, run_text

ACC = "9999999999-25-000008"


def _doc(ordinal: int, section: str = "mdna") -> str:
    return f"{ACC}/{section}/{ordinal}"


def _q(qid: str, ticker: str) -> RetQuestion:
    return RetQuestion(
        id=qid, ticker=ticker, question=f"question {qid}", written_on=dt.date(2026, 1, 1)
    )


def _hits(system: str, rankings: dict[str, list[str]]) -> list[RunHit]:
    return [
        RunHit(qid=qid, chunk=ChunkRef.parse(docid), rank=rank, score=1 / rank, system=system)
        for qid, docids in rankings.items()
        for rank, docid in enumerate(docids, start=1)
    ]


def test_oracle_ranks_by_grade_then_docid_and_drops_grade_zero() -> None:
    judged = {_doc(3): 1, _doc(1): 2, _doc(2): 0, _doc(0): 2}
    assert oracle_ranking(judged, depth=10) == [_doc(0), _doc(1), _doc(3)]
    assert oracle_ranking(judged, depth=1) == [_doc(0)]


def test_random_ranking_is_seeded_per_question() -> None:
    docids = [_doc(i) for i in range(20)]
    first = random_ranking(docids, seed=5, qid="q1", depth=10)
    assert first == random_ranking(list(reversed(docids)), seed=5, qid="q1", depth=10)
    assert first != random_ranking(docids, seed=5, qid="q2", depth=10)
    assert len(first) == 10
    assert set(first) <= set(docids)


def test_run_text_round_trips_through_parse_run() -> None:
    hits = _hits("bm25", {"q1": [_doc(0), _doc(4)], "q2": [_doc(1, "risk_factors")]})
    text = run_text(hits)
    assert text.splitlines()[0] == f"q1 Q0 {_doc(0)} 1 1.000000 bm25"
    assert parse_run(text) == hits


def test_collect_runs_asks_each_ranker_with_the_question_company() -> None:
    calls: list[tuple[str, str, int]] = []

    def ranker(question: RetQuestion, cik: str, depth: int) -> list[tuple[ChunkRef, float]]:
        calls.append((question.id, cik, depth))
        return [(ChunkRef.parse(_doc(9)), 0.5), (ChunkRef.parse(_doc(8)), 0.25)]

    questions = [_q("q1", "AAA"), _q("q2", "BBB")]
    hits = collect_runs(questions, {"x": ranker}, {"AAA": "0000000001", "BBB": "0000000002"}, 7)
    assert calls == [("q1", "0000000001", 7), ("q2", "0000000002", 7)]
    assert [(h.qid, h.rank, h.chunk.docid, h.system) for h in hits[:2]] == [
        ("q1", 1, _doc(9), "x"),
        ("q1", 2, _doc(8), "x"),
    ]


QUESTIONS = [_q("q1", "AAA"), _q("q2", "AAA"), _q("q3", "BBB"), _q("q4", "BBB")]
QRELS = {
    "q1": {_doc(0): 2, _doc(1): 1},
    "q2": {_doc(2): 1},
    "q3": {_doc(3): 2},
    "q4": {_doc(4): 0},  # pooled but nothing relevant: not scored
}
GOOD = {"q1": [_doc(0), _doc(1)], "q2": [_doc(2)], "q3": [_doc(3)], "q4": [_doc(4)]}
BAD = {"q1": [_doc(9), _doc(1)], "q2": [_doc(9)]}  # q3 missing: scores zero


def test_report_means_over_scored_questions() -> None:
    hits = _hits("good", GOOD) + _hits("bad", BAD)
    report = retrieval_report(QUESTIONS, QRELS, hits, baseline=None, resamples=200, seed=1)
    assert (report.questions, report.scored, report.unscored) == (4, 3, ("q4",))
    by_system = {s.system: s for s in report.systems}
    assert list(by_system) == ["bad", "good"]
    assert by_system["good"].metrics["recall@5"].estimate == pytest.approx(1.0)
    assert by_system["bad"].metrics["recall@5"].estimate == pytest.approx((0.5 + 0 + 0) / 3)
    assert by_system["bad"].metrics["mrr@10"].estimate == pytest.approx((0.5 + 0 + 0) / 3)
    assert by_system["good"].metrics["ndcg@10"].clusters == 2
    assert report.comparisons == ()


def test_report_compares_every_system_with_the_baseline() -> None:
    hits = _hits("good", GOOD) + _hits("bad", BAD)
    report = retrieval_report(QUESTIONS, QRELS, hits, baseline="bad", resamples=200, seed=1)
    assert [(c.system, c.baseline, c.metric) for c in report.comparisons] == [
        ("good", "bad", "recall@5"),
        ("good", "bad", "ndcg@10"),
        ("good", "bad", "mrr@10"),
    ]
    assert report.comparisons[0].result.estimate == pytest.approx(1.0 - 0.5 / 3)


def test_report_with_the_oracle() -> None:
    report = retrieval_report(
        QUESTIONS, QRELS, _hits("bad", BAD), baseline=None, resamples=50, seed=1, oracle=True
    )
    oracle = next(s for s in report.systems if s.system == "oracle")
    assert oracle.metrics["ndcg@10"].estimate == pytest.approx(1.0)


def test_report_rejects_unknown_baseline_and_questions() -> None:
    hits = _hits("good", GOOD)
    with pytest.raises(ValueError, match="baseline"):
        retrieval_report(QUESTIONS, QRELS, hits, baseline="nope", resamples=10, seed=1)
    with pytest.raises(ValueError, match="not in the questions"):
        retrieval_report(QUESTIONS[:1], QRELS, hits, baseline=None, resamples=10, seed=1)


def test_report_needs_some_relevant_chunk() -> None:
    with pytest.raises(ValueError, match="no question has a relevant chunk"):
        retrieval_report(
            QUESTIONS,
            {"q4": {_doc(4): 0}},
            _hits("good", GOOD),
            baseline=None,
            resamples=10,
            seed=1,
        )
