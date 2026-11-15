"""R1 baselines as rankers, and turning rankers into TREC runs.

A ranker gets a G-ret question, the 10-digit CIK of its company, and a depth, and returns
chunks best first with a score. Every baseline searches only that company's chunks: a
G-ret question names its company, as a `search_filings` call will. `random` orders the
company's chunks by a seeded hash (the floor); `oracle` orders the judged relevant chunks
by grade (the ceiling, computed from qrels at scoring time, never written as a run).
"""

from collections.abc import Callable, Mapping, Sequence

from sec_agent.golden.gret.models import ChunkRef, RetQuestion, RunHit
from sec_agent.golden.ranking import seeded_key

Ranker = Callable[[RetQuestion, str, int], list[tuple[ChunkRef, float]]]
RANDOM_SEED = 20261117
ORACLE = "oracle"


def random_ranking(docids: Sequence[str], *, seed: int, qid: str, depth: int) -> list[str]:
    """`depth` docids in an order fixed by seed and question, independent of input order."""
    return sorted(docids, key=lambda d: seeded_key(seed, "random", qid, d))[:depth]


def oracle_ranking(judged: Mapping[str, int], *, depth: int) -> list[str]:
    """Relevant docids, highest grade first, then by docid."""
    relevant = [(g, d) for d, g in judged.items() if g >= 1]
    return [d for _, d in sorted(relevant, key=lambda gd: (-gd[0], gd[1]))][:depth]


def collect_runs(
    questions: Sequence[RetQuestion],
    rankers: Mapping[str, Ranker],
    cik_of: Mapping[str, str],
    depth: int,
) -> list[RunHit]:
    """Every ranker on every question; `cik_of` maps a question's ticker to its CIK."""
    hits: list[RunHit] = []
    for system, ranker in rankers.items():
        for question in questions:
            ranked = ranker(question, cik_of[question.ticker], depth)
            hits += [
                RunHit(qid=question.id, chunk=ref, rank=rank, score=score, system=system)
                for rank, (ref, score) in enumerate(ranked[:depth], start=1)
            ]
    return hits
