"""b1's passages: a search of the pinned retrieval space, filtered to the question's companies.

Hybrid by default; BM25 alone when there is no query embedder (`--lexical`), since dense
and hybrid search refuse to run without one.
"""

from sec_agent.edgar.urls import normalize_cik
from sec_agent.eval.numeric.baselines import Passage
from sec_agent.golden.gnum.models import NumQuestion
from sec_agent.pg_pool import Connections, lease
from sec_agent.retrieval.embedder import Embedder
from sec_agent.retrieval.models import EmbeddingSpace, SearchFilters, SearchMode
from sec_agent.retrieval.search import search


class SearchPassages:
    def __init__(
        self,
        conns: Connections,
        space: EmbeddingSpace,
        embedder: Embedder | None,
        *,
        mode: SearchMode | None = None,
    ) -> None:
        """`mode` None: hybrid with an embedder, lexical without one."""
        self._conns = conns
        self._space = space
        self._embedder = embedder
        self._mode: SearchMode = mode or ("lexical" if embedder is None else "hybrid")

    def passages(self, question: NumQuestion, k: int) -> list[Passage]:
        with lease(self._conns) as conn:
            hits = search(
                conn,
                question.question,
                self._space,
                embedder=self._embedder,
                mode=self._mode,
                filters=SearchFilters(ciks=tuple(normalize_cik(c) for c in question.ciks)),
                k=k,
            )
        return [Passage(docid=f"{h.accession}/{h.section}/{h.ordinal}", text=h.text) for h in hits]
