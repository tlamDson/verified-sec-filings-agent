r"""The lexical arm: Okapi BM25 in plain SQL over Postgres full-text lexemes.

    score(d, q) = sum over query lexemes t in d of
        idf(t) * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(d) / avg_len))
    idf(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))        (Lucene's non-negative idf)

Lexemes come from `to_tsvector('english', ...)` (stemmed, stop words removed), `tf` is the
number of positions of a lexeme in the chunk and `len(d)` the sum over its lexemes. N, df and
avg_len are per index_version, rebuilt by `refresh_lexical`. Why not pg_search: plain SQL runs
the same on the local ParadeDB image, the test Postgres and a managed free-tier Postgres, and
a test checks every score against a Python BM25 over the same lexemes.

The query is never parsed as tsquery syntax: its lexemes are extracted with to_tsvector, then
quoted (quotes and backslashes doubled) and joined with `|`.
"""

from typing import Any

import psycopg
from psycopg import sql

from sec_agent.retrieval.filters import filter_condition
from sec_agent.retrieval.models import SearchFilters

TS_CONFIG = "english"
BM25_K1 = 1.2
BM25_B = 0.75

_LOCK_VERSION = b"SELECT pg_advisory_xact_lock(hashtextextended(%s, 5))"

_INSERT_MISSING = b"""
INSERT INTO chunk_lexical (index_version, accession, section, ordinal, tsv, doc_len)
SELECT c.index_version, c.accession, c.section, c.ordinal, v.tsv,
       (SELECT coalesce(sum(cardinality(t.positions)), 0) FROM unnest(v.tsv) AS t)
FROM chunks c
CROSS JOIN LATERAL (SELECT to_tsvector('english', c.text) AS tsv) AS v
WHERE c.index_version = %(version)s
  AND NOT EXISTS (
      SELECT 1 FROM chunk_lexical l
      WHERE l.index_version = c.index_version AND l.accession = c.accession
        AND l.section = c.section AND l.ordinal = c.ordinal)
ON CONFLICT DO NOTHING
"""
_DELETE_DF = b"DELETE FROM lexical_df WHERE index_version = %(version)s"
_INSERT_DF = b"""
INSERT INTO lexical_df (index_version, lexeme, df)
SELECT l.index_version, t.lexeme, count(*)
FROM chunk_lexical l CROSS JOIN LATERAL unnest(l.tsv) AS t
WHERE l.index_version = %(version)s
GROUP BY l.index_version, t.lexeme
"""
_UPSERT_STATS = b"""
INSERT INTO lexical_stats (index_version, ts_config, doc_count, total_len, avg_doc_len)
SELECT %(version)s, 'english', count(*), coalesce(sum(doc_len), 0),
       CASE WHEN count(*) = 0 THEN 0 ELSE coalesce(sum(doc_len), 0)::float8 / count(*) END
FROM chunk_lexical WHERE index_version = %(version)s
ON CONFLICT (index_version) DO UPDATE
SET ts_config = EXCLUDED.ts_config, doc_count = EXCLUDED.doc_count,
    total_len = EXCLUDED.total_len, avg_doc_len = EXCLUDED.avg_doc_len, built_at = now()
"""
_COUNT_ROWS = b"SELECT count(*) FROM chunk_lexical WHERE index_version = %(version)s"


def refresh_lexical(conn: psycopg.Connection[Any], index_version: str) -> int:
    """Add missing lexical rows, then rebuild df and averages; return the version's rows."""
    params = {"version": index_version}
    with conn.transaction():
        conn.execute(_LOCK_VERSION, (index_version,))
        conn.execute(_INSERT_MISSING, params)
        conn.execute(_DELETE_DF, params)
        conn.execute(_INSERT_DF, params)
        conn.execute(_UPSERT_STATS, params)
        row = conn.execute(_COUNT_ROWS, params).fetchone()
    assert row is not None
    return int(row[0])


_ARM = r"""
WITH terms AS (
    SELECT DISTINCT t.lexeme FROM unnest(to_tsvector('english', %(query)s)) AS t
), tsq AS (
    SELECT string_agg(
               '''' || replace(replace(lexeme, '\', '\\'), '''', '''''') || '''', ' | '
           )::tsquery AS q
    FROM terms
), stats AS (
    SELECT doc_count, avg_doc_len FROM lexical_stats WHERE index_version = %(version)s
), idf AS (
    SELECT d.lexeme,
           ln(1::float8 + (s.doc_count - d.df + 0.5::float8) / (d.df + 0.5::float8)) AS idf
    FROM lexical_df d JOIN terms ON terms.lexeme = d.lexeme CROSS JOIN stats s
    WHERE d.index_version = %(version)s
), matched AS (
    SELECT l.accession, l.section, l.ordinal, l.tsv, l.doc_len
    FROM chunk_lexical l
    JOIN chunks c ON c.index_version = l.index_version AND c.accession = l.accession
                 AND c.section = l.section AND c.ordinal = l.ordinal
    CROSS JOIN tsq
    WHERE l.index_version = %(version)s AND l.tsv @@ tsq.q {filters}
), scored AS (
    SELECT m.accession, m.section, m.ordinal,
           sum(i.idf * cardinality(t.positions) * ({k1}::float8 + 1)
               / (cardinality(t.positions)
                  + {k1}::float8
                    * (1 - {b}::float8 + {b}::float8 * m.doc_len / s.avg_doc_len))) AS bm25
    FROM matched m
    CROSS JOIN LATERAL unnest(m.tsv) AS t
    JOIN idf i ON i.lexeme = t.lexeme
    CROSS JOIN stats s
    GROUP BY m.accession, m.section, m.ordinal
)
SELECT accession, section, ordinal, bm25,
       row_number() OVER (ORDER BY bm25 DESC, accession COLLATE "C", section COLLATE "C",
                          ordinal) AS rnk
FROM scored
ORDER BY rnk
LIMIT %(limit)s
"""


def lexical_sql(filters: SearchFilters | None = None) -> sql.Composed:
    """The arm for one index_version. Parameters: `query`, `version`, `limit`, filters."""
    return sql.SQL(_ARM).format(
        filters=filter_condition(filters or SearchFilters()),
        k1=sql.Literal(BM25_K1),
        b=sql.Literal(BM25_B),
    )
