"""b1's passages: a search of the pinned retrieval space, filtered to the question's companies."""

from typing import Any

import psycopg

from sec_agent.edgar.urls import normalize_cik
from sec_agent.eval.numeric.baselines import Passage
from sec_agent.golden.gnum.models import NumQuestion
from sec_agent.retrieval.embedder import Embedder
from sec_agent.retrieval.models import EmbeddingSpace, SearchFilters, SearchMode
from sec_agent.retrieval.search import search


class SearchPassages:
    def __init__(
        self,
        conn: psycopg.Connection[Any],
        space: EmbeddingSpace,
        embedder: Embedder | None,
        *,
        mode: SearchMode = "hybrid",
    ) -> None:
        self._conn = conn
        self._space = space
        self._embedder = embedder
        self._mode: SearchMode = mode

    def passages(self, question: NumQuestion, k: int) -> list[Passage]:
        hits = search(
            self._conn,
            question.question,
            self._space,
            embedder=self._embedder,
            mode=self._mode,
            filters=SearchFilters(ciks=tuple(normalize_cik(c) for c in question.ciks)),
            k=k,
        )
        return [Passage(docid=f"{h.accession}/{h.section}/{h.ordinal}", text=h.text) for h in hits]
