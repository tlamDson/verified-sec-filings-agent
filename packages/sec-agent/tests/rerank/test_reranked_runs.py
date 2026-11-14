"""Reranked TREC runs: a base run's top `depth` per question, reordered by a fold's scorer."""

import datetime as dt

import pytest
from rerank_kit import FakeScorer, by_length

from sec_agent.golden.gret.models import ChunkRef, RetQuestion, RunHit
from sec_agent.rerank.reranked_runs import FoldScorer, LeakageError, rerank_runs

D = dt.date(2026, 11, 13)
QUESTIONS = [
    RetQuestion(id="q1", ticker="AAA", question="first?", written_on=D),
    RetQuestion(id="q2", ticker="BBB", question="second?", written_on=D),
]


def _ref(n: int) -> ChunkRef:
    return ChunkRef(accession="0000000001-24-000001", section="mdna", ordinal=n)


def _hit(qid: str, n: int, rank: int) -> RunHit:
    return RunHit(qid=qid, chunk=_ref(n), rank=rank, score=1.0 / rank, system="hybrid")


# q1: chunks 0..3 at ranks 1..4; q2: chunks 10, 11. Hits arrive shuffled.
BASE = [_hit("q1", 2, 3), _hit("q1", 0, 1), _hit("q2", 11, 2), _hit("q1", 3, 4), _hit("q1", 1, 2)]
BASE.append(_hit("q2", 10, 1))
TEXTS = {
    _ref(0).docid: "a",
    _ref(1).docid: "bbbb",
    _ref(2).docid: "cc",
    _ref(3).docid: "dddddd",
    _ref(10).docid: "x",
    _ref(11).docid: "yy",
}


def _docids(hits: list[RunHit], qid: str) -> list[str]:
    return [h.chunk.docid for h in sorted(hits, key=lambda h: h.rank) if h.qid == qid]


def test_reorders_the_top_depth_and_drops_the_rest() -> None:
    scorer = FakeScorer(by_length)
    hits = rerank_runs(
        QUESTIONS, BASE, TEXTS, lambda _t: FoldScorer(scorer, ()), depth=3, system="rr"
    )
    # q1 top 3 by base rank: chunks 0 (a), 1 (bbbb), 2 (cc): by length 1, 2, 0
    assert _docids(hits, "q1") == [_ref(1).docid, _ref(2).docid, _ref(0).docid]
    assert _docids(hits, "q2") == [_ref(11).docid, _ref(10).docid]
    q1 = sorted((h for h in hits if h.qid == "q1"), key=lambda h: h.rank)
    assert [h.rank for h in q1] == [1, 2, 3]
    assert [h.score for h in q1] == [4.0, 2.0, 1.0]
    assert {h.system for h in hits} == {"rr"}
    assert scorer.calls[0] == ("first?", ("a", "bbbb", "cc"))


def test_each_question_uses_the_scorer_of_its_company() -> None:
    long_first, short_first = FakeScorer(by_length), FakeScorer(lambda _q, p: -len(p))
    scorers = {"AAA": FoldScorer(long_first, ("BBB",)), "BBB": FoldScorer(short_first, ("AAA",))}
    hits = rerank_runs(QUESTIONS, BASE, TEXTS, scorers.__getitem__, depth=2, system="cv")
    assert _docids(hits, "q1") == [_ref(1).docid, _ref(0).docid]
    assert _docids(hits, "q2") == [_ref(10).docid, _ref(11).docid]
    assert [q for q, _ in long_first.calls] == ["first?"]
    assert [q for q, _ in short_first.calls] == ["second?"]


def test_a_scorer_trained_on_the_question_company_is_refused() -> None:
    leaky = FoldScorer(FakeScorer(by_length), ("AAA", "BBB"))
    with pytest.raises(LeakageError, match="AAA"):
        rerank_runs(QUESTIONS, BASE, TEXTS, lambda _t: leaky, depth=2, system="cv")


def test_a_candidate_without_text_is_refused() -> None:
    texts = {k: v for k, v in TEXTS.items() if k != _ref(1).docid}
    with pytest.raises(ValueError, match="no text"):
        rerank_runs(
            QUESTIONS,
            BASE,
            texts,
            lambda _t: FoldScorer(FakeScorer(by_length), ()),
            depth=2,
            system="rr",
        )


def test_a_question_without_base_hits_has_no_reranked_hits() -> None:
    only_q1 = [h for h in BASE if h.qid == "q1"]
    scorer = FoldScorer(FakeScorer(by_length), ())
    hits = rerank_runs(QUESTIONS, only_q1, TEXTS, lambda _t: scorer, depth=2, system="rr")
    assert {h.qid for h in hits} == {"q1"}


def test_a_base_run_of_two_systems_is_refused() -> None:
    mixed = [*BASE, RunHit(qid="q1", chunk=_ref(0), rank=1, score=1.0, system="bm25")]
    scorer = FoldScorer(FakeScorer(by_length), ())
    with pytest.raises(ValueError, match="one system"):
        rerank_runs(QUESTIONS, mixed, TEXTS, lambda _t: scorer, depth=2, system="rr")
