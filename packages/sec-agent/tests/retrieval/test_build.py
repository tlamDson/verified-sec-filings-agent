"""build_index: embed every chunk of a version once, then the HNSW and BM25 statistics."""

import math
from typing import Any

import psycopg
import pytest
from retrieval_corpus import CONFIG, FILING_10K, FIXTURES, OTHER_VERSION, VERSION
from retrieval_fakes import HASH_SPEC, HashEmbedder, hash_vector

from sec_agent.filings.pipeline import index_filing
from sec_agent.filings.store import PostgresChunkStore
from sec_agent.retrieval.build import build_index
from sec_agent.retrieval.errors import EmbeddingMismatchError
from sec_agent.retrieval.space import hnsw_index_name, make_space

Conn = psycopg.Connection[Any]


def _scalar(conn: Conn, query: str, *params: object) -> Any:
    row = conn.execute(query.encode(), params).fetchone()
    assert row is not None
    return row[0]


def _chunk_count(conn: Conn, version: str) -> int:
    return int(_scalar(conn, "SELECT count(*) FROM chunks WHERE index_version = %s", version))


def test_build_embeds_every_chunk_of_the_version_once(conn: Conn, embedder: HashEmbedder) -> None:
    total = _chunk_count(conn, VERSION)
    report = build_index(conn, VERSION, embedder, batch_size=4)
    space = make_space(VERSION, HASH_SPEC)
    assert (report.space, report.index_version) == (space.name, VERSION)
    assert (report.chunks, report.embedded, report.already_embedded) == (total, total, 0)
    assert len(embedder.encoded) == total
    assert max(len(batch) for batch in embedder.batches) == 4
    assert all(text.startswith("passage: ") for text in embedder.encoded)
    stored = _scalar(conn, "SELECT count(*) FROM chunk_embeddings WHERE space = %s", space.name)
    assert stored == total


def test_stored_vector_is_the_passage_embedding(conn: Conn, embedder: HashEmbedder) -> None:
    build_index(conn, VERSION, embedder)
    row = conn.execute(
        b"SELECT c.text, e.embedding::text FROM chunk_embeddings e JOIN chunks c"
        b" USING (index_version, accession, section, ordinal) WHERE e.index_version = %s"
        b" ORDER BY c.accession, c.section, c.ordinal LIMIT 1",
        (VERSION,),
    ).fetchone()
    assert row is not None
    stored = [float(v) for v in str(row[1]).strip("[]").split(",")]
    expected = hash_vector("passage: " + str(row[0]), HASH_SPEC.dimensions)
    assert stored == pytest.approx(expected, abs=1e-6)


def test_second_build_embeds_nothing(conn: Conn) -> None:
    build_index(conn, VERSION, HashEmbedder())
    again = HashEmbedder()
    report = build_index(conn, VERSION, again)
    assert (report.embedded, report.already_embedded) == (0, report.chunks)
    assert again.batches == []


def test_build_touches_only_its_version(conn: Conn, embedder: HashEmbedder) -> None:
    build_index(conn, VERSION, embedder)
    other = make_space(OTHER_VERSION, HASH_SPEC).name
    assert _scalar(conn, "SELECT count(*) FROM chunk_embeddings WHERE space = %s", other) == 0
    assert (
        _scalar(conn, "SELECT count(*) FROM lexical_stats WHERE index_version = %s", OTHER_VERSION)
        == 0
    )


def test_reingested_filing_is_re_embedded_and_nothing_else(conn: Conn, corpus_db: str) -> None:
    build_index(conn, VERSION, HashEmbedder())
    indexed = index_filing((FIXTURES / "sim-10k.htm").read_bytes(), FILING_10K, CONFIG)
    with PostgresChunkStore.connect(corpus_db) as store:
        store.replace(indexed)  # a second delivery of the job: rows deleted and re-inserted
    again = HashEmbedder()
    report = build_index(conn, VERSION, again)
    assert report.embedded == len(indexed.chunks)
    assert sorted(again.encoded) == sorted("passage: " + c.text for c in indexed.chunks)


def test_wrong_dimension_from_the_model_writes_nothing(conn: Conn) -> None:
    with pytest.raises(EmbeddingMismatchError):
        build_index(conn, VERSION, HashEmbedder(wrong_dimensions=True))
    assert _scalar(conn, "SELECT count(*) FROM chunk_embeddings") == 0


def test_hnsw_index_is_created_for_the_space(conn: Conn, embedder: HashEmbedder) -> None:
    build_index(conn, VERSION, embedder)
    space = make_space(VERSION, HASH_SPEC)
    definition = _scalar(
        conn,
        "SELECT indexdef FROM pg_indexes WHERE indexname = %s",
        hnsw_index_name(space.name),
    )
    assert "hnsw" in definition
    assert "vector_cosine_ops" in definition
    assert f"vector({HASH_SPEC.dimensions})" in definition
    assert space.name in definition  # partial index: this space only


def test_truncated_passages_are_counted(conn: Conn, embedder: HashEmbedder) -> None:
    report = build_index(conn, VERSION, embedder)
    texts = [
        str(r[0])
        for r in conn.execute(b"SELECT text FROM chunks WHERE index_version = %s", (VERSION,))
    ]
    limit = HASH_SPEC.max_input_tokens
    assert limit is not None
    expected = sum(1 for n in embedder.count_tokens(["passage: " + t for t in texts]) if n > limit)
    assert expected > 0  # the fixture has passages longer than the fake model's limit
    assert report.truncated == expected


def test_lexical_statistics_describe_the_version(conn: Conn, embedder: HashEmbedder) -> None:
    report = build_index(conn, VERSION, embedder)
    total = _chunk_count(conn, VERSION)
    assert report.lexical_rows == total
    row = conn.execute(
        b"SELECT doc_count, avg_doc_len FROM lexical_stats WHERE index_version = %s", (VERSION,)
    ).fetchone()
    lengths = [
        int(r[0])
        for r in conn.execute(
            b"SELECT (SELECT coalesce(sum(cardinality(t.positions)), 0)"
            b" FROM unnest(to_tsvector('english', c.text)) t)"
            b" FROM chunks c WHERE c.index_version = %s",
            (VERSION,),
        )
    ]
    assert row is not None
    assert row[0] == total
    assert math.isclose(float(row[1]), sum(lengths) / total)
    df = _scalar(
        conn,
        "SELECT df FROM lexical_df WHERE index_version = %s AND lexeme = 'widget'",
        VERSION,
    )
    with_widget = _scalar(
        conn,
        "SELECT count(*) FROM chunks WHERE index_version = %s"
        " AND to_tsvector('english', text) @@ 'widget'::tsquery",
        VERSION,
    )
    assert df == with_widget > 0


def test_statistics_follow_the_chunks_on_rebuild(conn: Conn) -> None:
    build_index(conn, VERSION, HashEmbedder())
    conn.execute(b"DELETE FROM indexed_filings WHERE accession = %s", (FILING_10K.accession,))
    report = build_index(conn, VERSION, HashEmbedder())
    total = _chunk_count(conn, VERSION)
    assert report.chunks == total
    assert (
        _scalar(conn, "SELECT doc_count FROM lexical_stats WHERE index_version = %s", VERSION)
        == total
    )
