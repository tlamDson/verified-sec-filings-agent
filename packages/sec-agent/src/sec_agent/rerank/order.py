"""The reranked order of passages: best score first, ties kept in retrieval order."""

import math
from collections.abc import Sequence


def rerank_order(scores: Sequence[float]) -> list[int]:
    """Indices into `scores`, best first; equal scores keep their input (retrieval) order."""
    if not all(math.isfinite(s) for s in scores):
        raise ValueError("rerank scores must be finite")
    return sorted(range(len(scores)), key=lambda i: (-scores[i], i))
