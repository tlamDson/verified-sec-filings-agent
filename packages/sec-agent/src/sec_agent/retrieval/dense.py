"""The dense arm: nearest chunks by cosine distance, ranked 1..limit.

Without filters the query walks the space's partial HNSW index (approximate; `hnsw.ef_search`
is raised to cover the request). With filters it ranks every matching chunk exactly: an
approximate index scan followed by a selective filter (one company of fifty) would silently
return fewer than `limit` rows, and the filtered sets are small enough to scan.

Parameters: `qvec` (pgvector text) and `limit`, plus the filter parameters when filtered.
Exactly tied distances (the same boilerplate in two filings) rank by chunk key; the HNSW
branch fetches twice `limit` candidates so ties at the cut-off are broken the same way.
"""

from psycopg import sql

from sec_agent.retrieval.filters import filter_condition
from sec_agent.retrieval.models import EmbeddingSpace, SearchFilters

MAX_EF_SEARCH = 1000  # pgvector's upper bound for hnsw.ef_search

_TIE_BREAK = 'accession COLLATE "C", section COLLATE "C", ordinal'

_UNFILTERED = """
SELECT accession, section, ordinal, distance,
       row_number() OVER (ORDER BY distance, {tie_break}) AS rnk
FROM (
    SELECT e.accession, e.section, e.ordinal,
           e.embedding::vector({dims}) <=> %(qvec)s::vector({dims}) AS distance
    FROM chunk_embeddings e
    WHERE e.space = {space}
    ORDER BY e.embedding::vector({dims}) <=> %(qvec)s::vector({dims})
    LIMIT least(2 * %(limit)s, {max_ef})
) AS nearest
ORDER BY rnk
LIMIT %(limit)s
"""

_FILTERED = """
SELECT accession, section, ordinal, distance,
       row_number() OVER (ORDER BY distance, {tie_break}) AS rnk
FROM (
    SELECT accession, section, ordinal,
           embedding::vector({dims}) <=> %(qvec)s::vector({dims}) AS distance
    FROM (
        SELECT e.accession, e.section, e.ordinal, e.embedding
        FROM chunk_embeddings e
        JOIN chunks c ON c.index_version = e.index_version AND c.accession = e.accession
                     AND c.section = e.section AND c.ordinal = e.ordinal
        WHERE e.space = {space} {filters}
        OFFSET 0  -- a fence: filter first, so no index scan on the distance can run
    ) AS candidates
) AS ranked
ORDER BY rnk
LIMIT %(limit)s
"""


def dense_sql(
    space: EmbeddingSpace, filters: SearchFilters | None = None, *, filtered: bool | None = None
) -> sql.Composed:
    """The arm for `space`; `filtered` defaults to whether `filters` sets anything."""
    filters = filters or SearchFilters()
    use_filter = (not filters.is_empty) if filtered is None else filtered
    template = _FILTERED if use_filter else _UNFILTERED
    # Space and dimension are literals: the planner must see them to match the partial index
    # `WHERE space = '<name>'` on `embedding::vector(<dims>)`; a typmod cannot be a parameter.
    return sql.SQL(template).format(
        dims=sql.Literal(int(space.spec.dimensions)),
        space=sql.Literal(space.name),
        tie_break=sql.SQL(_TIE_BREAK),
        max_ef=sql.Literal(MAX_EF_SEARCH),
        filters=filter_condition(filters),
    )


def ef_search(limit: int) -> int:
    return min(MAX_EF_SEARCH, max(40, 2 * limit))
