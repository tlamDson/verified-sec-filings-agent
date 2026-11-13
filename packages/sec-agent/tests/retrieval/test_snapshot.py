"""Snapshots: a named, verified state of one embedding space that eval runs pin to."""

from pathlib import Path
from typing import Any

import psycopg
import pytest
from retrieval_corpus import FILING_10Q, VERSION
from retrieval_fakes import HASH_SPEC, HashEmbedder

from sec_agent.retrieval.build import build_index
from sec_agent.retrieval.errors import (
    IncompleteIndexError,
    IndexNotBuiltError,
    SnapshotMismatchError,
    SnapshotNotFoundError,
)
from sec_agent.retrieval.models import EmbeddingSpace, Snapshot
from sec_agent.retrieval.search import search
from sec_agent.retrieval.snapshot import (
    activate,
    create_snapshot,
    load_snapshot,
    read_manifest,
    serving_snapshot,
    verify_snapshot,
    write_manifest,
)
from sec_agent.retrieval.space import make_space

Conn = psycopg.Connection[Any]


@pytest.fixture
def space(conn: Conn, embedder: HashEmbedder) -> EmbeddingSpace:
    build_index(conn, VERSION, embedder)
    return make_space(VERSION, HASH_SPEC)


def _count(conn: Conn, version: str, column: str = "*") -> int:
    row = conn.execute(
        f"SELECT count({column}) FROM chunks WHERE index_version = %s".encode(), (version,)
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_snapshot_records_the_space_and_its_content(conn: Conn, space: EmbeddingSpace) -> None:
    snapshot = create_snapshot(conn, "eval-2026-11", space)
    assert (snapshot.name, snapshot.space, snapshot.index_version) == (
        "eval-2026-11",
        space.name,
        VERSION,
    )
    assert snapshot.spec == HASH_SPEC
    assert snapshot.chunk_count == _count(conn, VERSION)
    assert snapshot.filing_count == _count(conn, VERSION, "DISTINCT accession")
    assert len(snapshot.content_sha256) == 64
    assert load_snapshot(conn, "eval-2026-11") == snapshot


def test_same_content_gives_the_same_digest(conn: Conn, space: EmbeddingSpace) -> None:
    first = create_snapshot(conn, "a", space)
    second = create_snapshot(conn, "b", space)
    assert first.content_sha256 == second.content_sha256


def test_creating_the_same_snapshot_again_is_a_no_op(conn: Conn, space: EmbeddingSpace) -> None:
    first = create_snapshot(conn, "eval", space)
    assert create_snapshot(conn, "eval", space) == first


def test_a_name_never_moves_to_other_content(conn: Conn, space: EmbeddingSpace) -> None:
    create_snapshot(conn, "eval", space)
    conn.execute(b"DELETE FROM indexed_filings WHERE accession = %s", (FILING_10Q.accession,))
    build_index(conn, VERSION, HashEmbedder())
    with pytest.raises(SnapshotMismatchError, match="eval"):
        create_snapshot(conn, "eval", space)


def test_snapshot_of_an_incomplete_index_is_refused(conn: Conn, space: EmbeddingSpace) -> None:
    conn.execute(
        b"DELETE FROM chunk_embeddings WHERE space = %s AND accession = %s",
        (space.name, FILING_10Q.accession),
    )
    with pytest.raises(IncompleteIndexError, match="3 of"):
        create_snapshot(conn, "eval", space)


def test_snapshot_of_stale_lexical_statistics_is_refused(conn: Conn, space: EmbeddingSpace) -> None:
    conn.execute(b"UPDATE lexical_stats SET doc_count = doc_count + 1")
    with pytest.raises(IncompleteIndexError, match="lexical"):
        create_snapshot(conn, "eval", space)


def test_snapshot_of_an_unbuilt_space_is_refused(conn: Conn) -> None:
    with pytest.raises(IndexNotBuiltError):
        create_snapshot(conn, "eval", make_space(VERSION, HASH_SPEC))


def test_verify_passes_until_the_content_changes(conn: Conn, space: EmbeddingSpace) -> None:
    snapshot = create_snapshot(conn, "eval", space)
    verify_snapshot(conn, snapshot)
    conn.execute(
        b"UPDATE chunk_embeddings SET embedding = embedding + embedding"
        b" WHERE space = %s AND accession = %s AND ordinal = 0",
        (space.name, FILING_10Q.accession),
    )
    with pytest.raises(SnapshotMismatchError, match="changed"):
        verify_snapshot(conn, snapshot)


def test_verify_catches_a_removed_filing(conn: Conn, space: EmbeddingSpace) -> None:
    snapshot = create_snapshot(conn, "eval", space)
    conn.execute(b"DELETE FROM indexed_filings WHERE accession = %s", (FILING_10Q.accession,))
    with pytest.raises(SnapshotMismatchError):
        verify_snapshot(conn, snapshot)


def test_unknown_snapshot_is_an_error(conn: Conn) -> None:
    with pytest.raises(SnapshotNotFoundError, match="nope"):
        load_snapshot(conn, "nope")


def test_manifest_round_trips(conn: Conn, space: EmbeddingSpace, tmp_path: Path) -> None:
    snapshot = create_snapshot(conn, "eval", space)
    path = tmp_path / "snapshots" / "eval.json"
    write_manifest(snapshot, path)
    assert read_manifest(path) == snapshot
    assert path.read_text("utf-8").endswith("\n")


def test_activate_switches_the_serving_pointer(conn: Conn, space: EmbeddingSpace) -> None:
    assert serving_snapshot(conn) is None
    blue = create_snapshot(conn, "blue", space)
    activate(conn, "blue")
    assert serving_snapshot(conn) == blue
    green = create_snapshot(conn, "green", space)
    activate(conn, "green")
    assert serving_snapshot(conn) == green
    assert serving_snapshot(conn, "staging") is None


def test_activate_refuses_a_snapshot_whose_content_changed(
    conn: Conn, space: EmbeddingSpace
) -> None:
    create_snapshot(conn, "blue", space)
    activate(conn, "blue")
    create_snapshot(conn, "green", space)
    conn.execute(b"DELETE FROM indexed_filings WHERE accession = %s", (FILING_10Q.accession,))
    with pytest.raises(SnapshotMismatchError):
        activate(conn, "green")
    serving = serving_snapshot(conn)
    assert isinstance(serving, Snapshot)
    assert serving.name == "blue"


def test_search_through_a_snapshot_uses_its_space(
    conn: Conn, space: EmbeddingSpace, embedder: HashEmbedder
) -> None:
    snapshot = create_snapshot(conn, "eval", space)
    hits = search(conn, "net sales", snapshot.embedding_space, embedder=embedder, k=3)
    assert hits == search(conn, "net sales", space, embedder=embedder, k=3)
