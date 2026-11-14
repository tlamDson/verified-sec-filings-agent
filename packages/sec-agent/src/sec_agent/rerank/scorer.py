"""What a reranker model is to the rest of the code: one score per (query, passage) pair."""

from collections.abc import Sequence
from typing import Protocol


class PairScorer(Protocol):
    @property
    def name(self) -> str: ...

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        """One relevance score per passage, in passage order; higher is more relevant."""
        ...
