"""Rankers over the Postgres index: BM25, vector and hybrid through `search`, and random.

Each one reads only the question's company (a CIK filter) in the pinned embedding space.
"""

from typing import Any

import psycopg

from sec_agent.eval.retrieval.rankers import RANDOM_SEED, Ranker, random_ranking
from sec_agent.golden.gret.models import ChunkRef, RetQuestion
from sec_agent.retrieval.embedder import Embedder
from sec_agent.retrieval.models import EmbeddingSpace, SearchFilters, SearchMode
from sec_agent.retrieval.search import search

Conn = psycopg.Connection[Any]

_COMPANY_CHUNKS = b"""
SELECT accession, section, ordinal FROM chunks WHERE index_version = %s AND cik = %s
"""


class CompanyChunks:
    """Every chunk key of one company in one index version, read once per company."""

    def __init__(self, conn: Conn, index_version: str) -> None:
        self._conn = conn
        self._version = index_version
        self._cache: dict[str, list[str]] = {}

    def docids(self, cik: str) -> list[str]:
        if cik not in self._cache:
            rows = self._conn.execute(_COMPANY_CHUNKS, (self._version, cik)).fetchall()
            self._cache[cik] = [f"{a}/{s}/{o}" for a, s, o in rows]
        return self._cache[cik]


def random_ranker(chunks: CompanyChunks, *, seed: int = RANDOM_SEED) -> Ranker:
    def rank(question: RetQuestion, cik: str, depth: int) -> list[tuple[ChunkRef, float]]:
        order = random_ranking(chunks.docids(cik), seed=seed, qid=question.id, depth=depth)
        return [(ChunkRef.parse(d), 1 / i) for i, d in enumerate(order, start=1)]

    return rank


def search_ranker(
    conn: Conn,
    space: EmbeddingSpace,
    embedder: Embedder | None,
    mode: SearchMode,
    *,
    candidates: int = 50,
) -> Ranker:
    def rank(question: RetQuestion, cik: str, depth: int) -> list[tuple[ChunkRef, float]]:
        hits = search(
            conn,
            question.question,
            space,
            embedder=embedder,
            mode=mode,
            filters=SearchFilters(ciks=(cik,)),
            k=depth,
            candidates=max(candidates, depth),
        )
        return [
            (ChunkRef(accession=h.accession, section=h.section, ordinal=h.ordinal), h.score)
            for h in hits
        ]

    return rank
