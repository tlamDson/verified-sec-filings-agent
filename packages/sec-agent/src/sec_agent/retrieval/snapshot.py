"""Snapshots: a named, verified state of one embedding space, for eval runs and serving.

A snapshot records the space and a SHA-256 over every chunk of its index_version, in key
order: chunk key, the chunk's text hash, and the hash of its stored vector. It is taken only
when the index is complete (every chunk has a vector and a lexical row, and the BM25
statistics count exactly those rows). `verify_snapshot` recomputes the digest, so an eval run
can prove at its start and end that it read the content it reports; a name never moves to
other content. `activate` points a pointer ("serving") at a verified snapshot: the
blue/green switch is that one row.
"""

from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from sec_agent.retrieval.errors import (
    IncompleteIndexError,
    SnapshotMismatchError,
    SnapshotNotFoundError,
)
from sec_agent.retrieval.models import EmbedderSpec, EmbeddingSpace, Snapshot
from sec_agent.retrieval.space_store import require_space

SERVING = "serving"

_STATE = b"""
SELECT count(*) AS chunks,
       count(e.embedding) AS embedded,
       count(l.doc_len) AS lexical_rows,
       coalesce(sum(l.doc_len), 0) AS lexical_len,
       count(DISTINCT c.accession) AS filings,
       encode(sha256(convert_to(coalesce(string_agg(
           concat_ws(' ', c.accession, c.section, c.ordinal, c.text_sha256,
                     encode(sha256(convert_to(e.embedding::text, 'UTF8')), 'hex')),
           E'\n' ORDER BY c.accession COLLATE "C", c.section COLLATE "C", c.ordinal), ''),
           'UTF8')), 'hex') AS digest,
       (SELECT doc_count FROM lexical_stats WHERE index_version = %(version)s) AS stats_docs,
       (SELECT total_len FROM lexical_stats WHERE index_version = %(version)s) AS stats_len
FROM chunks c
LEFT JOIN chunk_embeddings e ON e.space = %(space)s AND e.accession = c.accession
                            AND e.section = c.section AND e.ordinal = c.ordinal
LEFT JOIN chunk_lexical l ON l.index_version = c.index_version AND l.accession = c.accession
                         AND l.section = c.section AND l.ordinal = c.ordinal
WHERE c.index_version = %(version)s
"""
_INSERT = b"""
INSERT INTO retrieval_snapshots (name, space, index_version, chunk_count, filing_count,
                                 content_sha256)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (name) DO NOTHING
"""
_SELECT = b"""
SELECT s.name, s.space, s.index_version, sp.spec, s.chunk_count, s.filing_count,
       s.content_sha256, s.created_at
FROM retrieval_snapshots s JOIN embedding_spaces sp ON sp.name = s.space
WHERE s.name = %s
"""
_POINT = b"""
INSERT INTO retrieval_pointers (name, snapshot) VALUES (%s, %s)
ON CONFLICT (name) DO UPDATE SET snapshot = EXCLUDED.snapshot, switched_at = now()
"""
_POINTER = b"SELECT snapshot FROM retrieval_pointers WHERE name = %s"


def create_snapshot(conn: psycopg.Connection[Any], name: str, space: EmbeddingSpace) -> Snapshot:
    """Record the current, complete state of `space` as `name`; idempotent for that state."""
    require_space(conn, space)
    chunks, filings, digest = _complete_state(conn, space)
    conn.execute(_INSERT, (name, space.name, space.index_version, chunks, filings, digest))
    snapshot = load_snapshot(conn, name)
    if (snapshot.space, snapshot.chunk_count, snapshot.content_sha256) != (
        space.name,
        chunks,
        digest,
    ):
        raise SnapshotMismatchError(
            f"snapshot {name} already exists for other content"
            f" ({snapshot.space}, {snapshot.content_sha256[:12]}); choose a new name"
        )
    return snapshot


def load_snapshot(conn: psycopg.Connection[Any], name: str) -> Snapshot:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(_SELECT, (name,)).fetchone()
    if row is None:
        raise SnapshotNotFoundError(f"no snapshot named {name}")
    return Snapshot.model_validate({**row, "spec": EmbedderSpec.model_validate(row["spec"])})


def verify_snapshot(conn: psycopg.Connection[Any], snapshot: Snapshot) -> None:
    """Raise SnapshotMismatchError unless the database still holds what `snapshot` recorded."""
    stored = load_snapshot(conn, snapshot.name)
    if stored != snapshot:
        raise SnapshotMismatchError(
            f"snapshot {snapshot.name} in the database differs from this one"
        )
    try:
        chunks, filings, digest = _complete_state(conn, snapshot.embedding_space)
    except IncompleteIndexError as error:
        raise SnapshotMismatchError(
            f"snapshot {snapshot.name}: content changed since it was taken ({error})"
        ) from error
    if (chunks, filings, digest) != (
        snapshot.chunk_count,
        snapshot.filing_count,
        snapshot.content_sha256,
    ):
        raise SnapshotMismatchError(
            f"snapshot {snapshot.name}: content changed since it was taken"
            f" ({snapshot.chunk_count} chunks, {snapshot.content_sha256[:12]} recorded;"
            f" {chunks} chunks, {digest[:12]} now)"
        )


def activate(conn: psycopg.Connection[Any], name: str, pointer: str = SERVING) -> Snapshot:
    """Verify snapshot `name`, then point `pointer` at it."""
    snapshot = load_snapshot(conn, name)
    verify_snapshot(conn, snapshot)
    conn.execute(_POINT, (pointer, name))
    return snapshot


def serving_snapshot(conn: psycopg.Connection[Any], pointer: str = SERVING) -> Snapshot | None:
    row = conn.execute(_POINTER, (pointer,)).fetchone()
    return None if row is None else load_snapshot(conn, str(row[0]))


def write_manifest(snapshot: Snapshot, path: Path) -> None:
    """The snapshot as JSON, for an eval run to commit beside its results."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")


def read_manifest(path: Path) -> Snapshot:
    return Snapshot.model_validate_json(path.read_text("utf-8"))


def _complete_state(conn: psycopg.Connection[Any], space: EmbeddingSpace) -> tuple[int, int, str]:
    """(chunks, filings, digest) of the space, or IncompleteIndexError saying what is missing."""
    # One statement, so the counts, digest and statistics come from one database snapshot.
    with conn.cursor(row_factory=dict_row) as cur:
        state = cur.execute(
            _STATE, {"space": space.name, "version": space.index_version}
        ).fetchone()
    assert state is not None
    chunks = int(state["chunks"])
    if chunks == 0:
        raise IncompleteIndexError(f"index version {space.index_version} has no chunks")
    if (missing := chunks - int(state["embedded"])) > 0:
        raise IncompleteIndexError(
            f"{missing} of {chunks} chunks have no vector in {space.name}; run the build"
        )
    lexical = (chunks, chunks, int(state["lexical_len"]))
    if (int(state["lexical_rows"]), state["stats_docs"], state["stats_len"]) != lexical:
        raise IncompleteIndexError(
            f"lexical rows or BM25 statistics of {space.index_version} are stale; run the build"
        )
    return chunks, int(state["filings"]), str(state["digest"])
