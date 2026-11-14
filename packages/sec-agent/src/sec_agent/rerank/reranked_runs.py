"""Reranked TREC runs for R1: a base run's top `depth` chunks per question, reordered.

Only the top `depth` are written: the reranker never sees deeper chunks, and the metrics
stop at rank 10. Each question is scored by the scorer of its company's fold, which must
not have been trained on that company.
"""

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from sec_agent.golden.gret.models import RetQuestion, RunHit
from sec_agent.rerank.order import rerank_order
from sec_agent.rerank.scorer import PairScorer


class LeakageError(ValueError):
    """A reranker would be scored on a company whose labels trained it."""


@dataclass(frozen=True)
class FoldScorer:
    scorer: PairScorer
    trained_on: tuple[str, ...]


def rerank_runs(
    questions: Sequence[RetQuestion],
    base: Sequence[RunHit],
    texts: Mapping[str, str],
    scorer_for: Callable[[str], FoldScorer],
    *,
    depth: int,
    system: str,
) -> list[RunHit]:
    """`scorer_for` maps a question's ticker to the scorer of its fold."""
    if len(systems := {h.system for h in base}) > 1:
        raise ValueError(f"a base run holds one system; got {sorted(systems)}")
    by_qid: defaultdict[str, list[RunHit]] = defaultdict(list)
    for hit in base:
        by_qid[hit.qid].append(hit)
    out: list[RunHit] = []
    for question in questions:
        ranked = sorted(by_qid.get(question.id, []), key=lambda h: (h.rank, h.chunk.docid))
        candidates = ranked[:depth]
        if not candidates:
            continue
        fold = scorer_for(question.ticker)
        if question.ticker in fold.trained_on:
            raise LeakageError(
                f"{question.id}: the reranker for {question.ticker} was trained on its labels"
            )
        if missing := [h.chunk.docid for h in candidates if h.chunk.docid not in texts]:
            raise ValueError(f"{question.id}: no text for {missing[:3]}")
        passages = [texts[h.chunk.docid] for h in candidates]
        scores = fold.scorer.score(question.question, passages)
        if len(scores) != len(passages):
            raise ValueError(f"{question.id}: {len(scores)} scores for {len(passages)} chunks")
        out += [
            RunHit(
                qid=question.id,
                chunk=candidates[i].chunk,
                rank=rank,
                score=scores[i],
                system=system,
            )
            for rank, i in enumerate(rerank_order(scores), start=1)
        ]
    return out
