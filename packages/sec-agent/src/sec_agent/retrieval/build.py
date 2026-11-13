"""build_index: make one chunk build searchable by one embedding model.

1. Register the space (index_version + model settings).
2. Embed every chunk of the version that has no vector in the space, in batches; each batch
   is checked (count, dimensions, finite, unit length) and written in one transaction.
3. Create the space's partial HNSW index.
4. Add missing lexical rows and rebuild the version's BM25 statistics.

Re-running is cheap and safe: only missing chunks are embedded (a filing re-ingested by its
job loses its vectors by cascade and is embedded again), inserts ignore rows another builder
wrote first, and statistics are recomputed from the rows present.
"""

from typing import Any

import psycopg
from psycopg import sql

from sec_agent.retrieval.embedder import Embedder, count_truncated, embed_passages
from sec_agent.retrieval.lexical import refresh_lexical
from sec_agent.retrieval.models import BuildReport, EmbeddingSpace
from sec_agent.retrieval.space import hnsw_index_name, make_space
from sec_agent.retrieval.space_store import register_space
from sec_agent.retrieval.vectors import vector_literal

HNSW_M = 16  # pgvector defaults, stated so a change is a visible diff
HNSW_EF_CONSTRUCTION = 64

_COUNT_CHUNKS = b"SELECT count(*) FROM chunks WHERE index_version = %s"
_COUNT_EMBEDDED = b"SELECT count(*) FROM chunk_embeddings WHERE space = %s"
_MISSING = b"""
SELECT c.accession, c.section, c.ordinal, c.text
FROM chunks c
WHERE c.index_version = %(version)s
  AND NOT EXISTS (
      SELECT 1 FROM chunk_embeddings e
      WHERE e.space = %(space)s AND e.accession = c.accession
        AND e.section = c.section AND e.ordinal = c.ordinal)
ORDER BY c.accession COLLATE "C", c.section COLLATE "C", c.ordinal
LIMIT %(limit)s
"""
_INSERT = b"""
INSERT INTO chunk_embeddings (space, index_version, accession, section, ordinal, embedding)
VALUES (%s, %s, %s, %s, %s, %s::vector)
ON CONFLICT DO NOTHING
"""
_LOCK_SPACE = b"SELECT pg_advisory_xact_lock(hashtextextended(%s, 6))"
_HNSW = """
CREATE INDEX IF NOT EXISTS {name} ON chunk_embeddings
USING hnsw ((embedding::vector({dims})) vector_cosine_ops)
WITH (m = {m}, ef_construction = {ef})
WHERE space = {space}
"""


def build_index(
    conn: psycopg.Connection[Any], index_version: str, embedder: Embedder, *, batch_size: int = 64
) -> BuildReport:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    space = make_space(index_version, embedder.spec)
    register_space(conn, space)
    chunks = _count(conn, _COUNT_CHUNKS, index_version)
    already = _count(conn, _COUNT_EMBEDDED, space.name)
    embedded = truncated = 0
    while batch := conn.execute(
        _MISSING, {"version": index_version, "space": space.name, "limit": batch_size}
    ).fetchall():
        texts = [str(row[3]) for row in batch]
        vectors = embed_passages(embedder, texts)
        truncated += count_truncated(embedder, texts)
        dims = space.spec.dimensions
        with conn.transaction(), conn.cursor() as cur:
            cur.executemany(
                _INSERT,
                [
                    (space.name, index_version, row[0], row[1], row[2], vector_literal(vec, dims))
                    for row, vec in zip(batch, vectors, strict=True)
                ],
            )
        embedded += len(batch)
    ensure_hnsw_index(conn, space)
    lexical_rows = refresh_lexical(conn, index_version)
    return BuildReport(
        index_version=index_version,
        space=space.name,
        chunks=chunks,
        embedded=embedded,
        already_embedded=already,
        truncated=truncated,
        lexical_rows=lexical_rows,
    )


def ensure_hnsw_index(conn: psycopg.Connection[Any], space: EmbeddingSpace) -> None:
    statement = sql.SQL(_HNSW).format(
        name=sql.Identifier(hnsw_index_name(space.name)),
        dims=sql.Literal(int(space.spec.dimensions)),
        m=sql.Literal(HNSW_M),
        ef=sql.Literal(HNSW_EF_CONSTRUCTION),
        space=sql.Literal(space.name),
    )
    with conn.transaction():
        conn.execute(_LOCK_SPACE, (space.name,))  # two builders: one creates, one finds it
        conn.execute(statement)


def _count(conn: psycopg.Connection[Any], query: bytes, value: str) -> int:
    row = conn.execute(query, (value,)).fetchone()
    assert row is not None
    return int(row[0])
