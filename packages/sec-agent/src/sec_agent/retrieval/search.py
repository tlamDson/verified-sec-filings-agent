"""search: dense, lexical (BM25) or hybrid retrieval over one embedding space, in one query.

Hybrid fuses the two arms with reciprocal rank fusion inside SQL: each arm ranks its top
`candidates` chunks, a full outer join adds 1 / (RRF_K + rank) per arm, and the result is
ordered by that sum, then by the best rank either arm gave, then by chunk key. That is the
order `rrf.rrf_fuse` defines; a test holds them equal.

Every query pins one space, so one index_version and one model: the stored space must match
the one asked for, and the query embedder must be the space's model (dimensions, prefixes,
normalisation), or the search is refused instead of returning silently wrong neighbours.
"""

from typing import Any, LiteralString

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from sec_agent.retrieval.dense import dense_sql, ef_search
from sec_agent.retrieval.embedder import Embedder, embed_query
from sec_agent.retrieval.errors import EmbeddingMismatchError, IndexNotBuiltError
from sec_agent.retrieval.filters import filter_params
from sec_agent.retrieval.lexical import BM25_B, BM25_K1, lexical_sql
from sec_agent.retrieval.models import EmbeddingSpace, Hit, SearchFilters, SearchMode
from sec_agent.retrieval.rrf import RRF_K
from sec_agent.retrieval.space_store import require_space
from sec_agent.retrieval.vectors import vector_literal

__all__ = ["BM25_B", "BM25_K1", "MAX_RESULTS", "search"]

MAX_RESULTS = 1000

_FUSE: dict[SearchMode, LiteralString] = {
    "hybrid": """
    SELECT accession, section, ordinal, d.rnk AS dense_rank, l.rnk AS lexical_rank,
           d.distance, l.bm25,
           coalesce(1::float8 / ({rrf_k} + d.rnk), 0)
               + coalesce(1::float8 / ({rrf_k} + l.rnk), 0) AS score
    FROM dense d FULL JOIN lexical l USING (accession, section, ordinal)
    """,
    "dense": """
    SELECT accession, section, ordinal, rnk AS dense_rank, NULL::bigint AS lexical_rank,
           distance, NULL::float8 AS bm25, 1 - distance AS score
    FROM dense
    """,
    "lexical": """
    SELECT accession, section, ordinal, NULL::bigint AS dense_rank, rnk AS lexical_rank,
           NULL::float8 AS distance, bm25, bm25 AS score
    FROM lexical
    """,
}

_QUERY = """
WITH {arms}, fused AS ({fuse})
SELECT f.score, f.dense_rank, f.lexical_rank, f.distance, f.bm25,
       c.index_version, c.accession, c.section, c.ordinal, c.cik, c.form, c.filing_date,
       c.report_date, c.char_start, c.char_end, c.text, fi.source_url
FROM fused f
JOIN chunks c ON c.index_version = %(version)s AND c.accession = f.accession
             AND c.section = f.section AND c.ordinal = f.ordinal
JOIN indexed_filings fi ON fi.index_version = c.index_version AND fi.accession = c.accession
ORDER BY f.score DESC,
         least(coalesce(f.dense_rank, {no_rank}), coalesce(f.lexical_rank, {no_rank})),
         f.accession COLLATE "C", f.section COLLATE "C", f.ordinal
LIMIT %(k)s
"""
_HAS_STATS = b"SELECT 1 FROM lexical_stats WHERE index_version = %s"
_SET_EF_SEARCH = b"SELECT set_config('hnsw.ef_search', %s, true)"


def search(
    conn: psycopg.Connection[Any],
    query: str,
    space: EmbeddingSpace,
    *,
    embedder: Embedder | None = None,
    mode: SearchMode = "hybrid",
    filters: SearchFilters | None = None,
    k: int = 10,
    candidates: int = 50,
) -> list[Hit]:
    """Top `k` chunks of `space` for `query`. Hybrid fuses each arm's top `candidates`."""
    for name, value in (("k", k), ("candidates", candidates)):
        if not 1 <= value <= MAX_RESULTS:
            raise ValueError(f"{name} must be between 1 and {MAX_RESULTS}, got {value}")
    filters = filters or SearchFilters()
    require_space(conn, space)
    uses_dense, uses_lexical = mode in ("dense", "hybrid"), mode in ("lexical", "hybrid")
    if uses_lexical and conn.execute(_HAS_STATS, (space.index_version,)).fetchone() is None:
        raise IndexNotBuiltError(f"BM25 statistics for {space.index_version} were never built")
    arm_limit = candidates if mode == "hybrid" else k
    params: dict[str, Any] = {
        **filter_params(filters),
        "query": query,
        "version": space.index_version,
        "limit": arm_limit,
        "k": k,
    }
    arms: list[sql.Composable] = []
    if uses_dense:
        params["qvec"] = _query_vector(query, space, embedder)
        arms.append(sql.SQL("dense AS ({})").format(dense_sql(space, filters)))
    if uses_lexical:
        arms.append(sql.SQL("lexical AS ({})").format(lexical_sql(filters)))
    statement = sql.SQL(_QUERY).format(
        arms=sql.SQL(", ").join(arms),
        fuse=sql.SQL(_FUSE[mode]).format(rrf_k=sql.Literal(RRF_K)),
        no_rank=sql.Literal(2**31 - 1),
    )
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        if uses_dense:
            cur.execute(_SET_EF_SEARCH, (str(ef_search(arm_limit)),))
        rows = cur.execute(statement, params).fetchall()
    return [Hit.model_validate({**row, "rank": rank}) for rank, row in enumerate(rows, start=1)]


def _query_vector(query: str, space: EmbeddingSpace, embedder: Embedder | None) -> str:
    if embedder is None:
        raise EmbeddingMismatchError("dense and hybrid search need the query embedder")
    if embedder.spec != space.spec:
        raise EmbeddingMismatchError(
            f"query embedder {embedder.spec.model} does not match space {space.name}"
            f" ({space.spec.model}); vectors from two models are not comparable"
        )
    return vector_literal(embed_query(embedder, query), space.spec.dimensions)
