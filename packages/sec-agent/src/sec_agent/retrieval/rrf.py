"""Reciprocal rank fusion (Cormack, Clarke and Buettcher, 2009), the reference for the SQL.

score(d) = sum over rankings of 1 / (k + rank of d), rank starting at 1. Ties break by the
best rank d reached in any ranking, then by key, so the order is total and reproducible.
`search` computes the same fusion in SQL; a test holds the two equal.
"""

from collections.abc import Sequence
from typing import Protocol, Self


class _Key(Protocol):
    def __lt__(self, other: Self, /) -> bool: ...

    def __hash__(self) -> int: ...


RRF_K = 60  # the constant from the paper; it damps the weight of the very top ranks


def rrf_fuse[K: _Key](rankings: Sequence[Sequence[K]], k: int = RRF_K) -> list[tuple[K, float]]:
    scores: dict[K, float] = {}
    best: dict[K, int] = {}
    for ranking in rankings:
        if len(set(ranking)) != len(ranking):
            raise ValueError("a ranking lists the same key twice")
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            best[key] = min(best.get(key, rank), rank)
    by_best = sorted(sorted(scores), key=lambda key: (-scores[key], best[key]))  # stable sort
    return [(key, scores[key]) for key in by_best]
