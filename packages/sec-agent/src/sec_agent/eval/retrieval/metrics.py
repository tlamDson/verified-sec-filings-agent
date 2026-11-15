"""Per-question retrieval metrics over graded judgements (0, 1, 2).

- A chunk is relevant at grade 1 or 2; an unjudged chunk is not relevant (TREC pooling).
- recall@k: relevant chunks in the top k over all relevant chunks of the question.
- nDCG@k: linear gain (the grade, as trec_eval's ndcg_cut), discount log2(rank + 1), over
  the ideal ordering of the judged grades cut at k.
- MRR@k: 1 / rank of the first relevant chunk within the top k, else 0.
- A repeated docid in a ranking counts only where it first appears.
A question with no relevant chunk has no score: it is left out and counted by the caller.
"""

import math
from collections.abc import Mapping, Sequence

METRICS: tuple[str, ...] = ("recall@5", "ndcg@10", "mrr@10")
RELEVANT = 1


def _top(ranking: Sequence[str], k: int) -> list[str]:
    return list(dict.fromkeys(ranking))[:k]


def recall_at(ranking: Sequence[str], judged: Mapping[str, int], k: int) -> float:
    relevant = {d for d, g in judged.items() if g >= RELEVANT}
    return len(relevant.intersection(_top(ranking, k))) / len(relevant)


def ndcg_at(ranking: Sequence[str], judged: Mapping[str, int], k: int) -> float:
    dcg = sum(judged.get(d, 0) / math.log2(i + 2) for i, d in enumerate(_top(ranking, k)))
    ideal_grades = sorted(judged.values(), reverse=True)[:k]
    ideal = sum(g / math.log2(i + 2) for i, g in enumerate(ideal_grades))
    return dcg / ideal


def reciprocal_rank(ranking: Sequence[str], judged: Mapping[str, int], k: int) -> float:
    for rank, docid in enumerate(_top(ranking, k), start=1):
        if judged.get(docid, 0) >= RELEVANT:
            return 1 / rank
    return 0.0


def query_scores(ranking: Sequence[str], judged: Mapping[str, int]) -> dict[str, float] | None:
    """The plan's three metrics for one question, or None when nothing judged is relevant."""
    if not any(g >= RELEVANT for g in judged.values()):
        return None
    return {
        "recall@5": recall_at(ranking, judged, 5),
        "ndcg@10": ndcg_at(ranking, judged, 10),
        "mrr@10": reciprocal_rank(ranking, judged, 10),
    }
