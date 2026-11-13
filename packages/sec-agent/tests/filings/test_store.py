"""PostgresChunkStore against a real Postgres: keyed, idempotent, one version beside another."""

from collections.abc import Callable, Iterator
from typing import LiteralString

import psycopg
import pytest

from sec_agent.filings.index_version import ChunkConfig
from sec_agent.filings.models import FilingRef, IndexedFiling
from sec_agent.filings.pipeline import index_filing
from sec_agent.filings.store import PostgresChunkStore, apply_schema


@pytest.fixture
def store(chunk_db: str) -> Iterator[PostgresChunkStore]:
    with PostgresChunkStore.connect(chunk_db) as s:
        yield s


@pytest.fixture
def indexed(read_fixture: Callable[[str], bytes], filing_10k: FilingRef) -> IndexedFiling:
    return index_filing(read_fixture("sim-10k.htm"), filing_10k, ChunkConfig(max_tokens=30))


def _count(db: str, table: LiteralString) -> int:
    with psycopg.connect(db) as conn:
        row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()
    assert row is not None
    return int(row[0])


def test_apply_schema_is_idempotent(chunk_db: str) -> None:
    with psycopg.connect(chunk_db, autocommit=True) as conn:
        apply_schema(conn)
        apply_schema(conn)


def test_replace_writes_filing_sections_and_chunks(
    store: PostgresChunkStore, chunk_db: str, indexed: IndexedFiling
) -> None:
    store.replace(indexed)
    assert _count(chunk_db, "indexed_filings") == 1
    assert _count(chunk_db, "filing_sections") == len(indexed.sections)
    assert _count(chunk_db, "chunks") == len(indexed.chunks)
    with psycopg.connect(chunk_db) as conn:
        row = conn.execute(
            "SELECT f.source_url, f.section_count, f.chunk_count, c.cik, c.form, c.report_date,"
            " c.text, substr(s.text, c.char_start + 1, c.char_end - c.char_start)"
            " FROM chunks c JOIN filing_sections s USING (index_version, accession, section)"
            " JOIN indexed_filings f USING (index_version, accession)"
            " WHERE c.section = 'risk_factors' AND c.ordinal = 0"
        ).fetchone()
    assert row is not None
    filing = indexed.filing
    assert row[:6] == (
        filing.document_url,
        len(indexed.sections),
        len(indexed.chunks),
        filing.cik,
        "10-K",
        filing.report_date,
    )
    assert row[6] == row[7]  # the chunk is the cited slice of its section


def test_replace_twice_leaves_one_copy(
    store: PostgresChunkStore, chunk_db: str, indexed: IndexedFiling
) -> None:
    store.replace(indexed)
    store.replace(indexed)
    assert _count(chunk_db, "indexed_filings") == 1
    assert _count(chunk_db, "chunks") == len(indexed.chunks)


def test_replace_drops_chunks_the_new_run_no_longer_has(
    store: PostgresChunkStore, chunk_db: str, indexed: IndexedFiling
) -> None:
    store.replace(indexed)
    fewer = indexed.model_copy(update={"chunks": indexed.chunks[:2]})
    store.replace(fewer)
    assert _count(chunk_db, "chunks") == 2


def test_filing_without_sections_is_still_recorded(
    store: PostgresChunkStore, chunk_db: str, indexed: IndexedFiling
) -> None:
    store.replace(indexed.model_copy(update={"sections": (), "chunks": ()}))
    assert _count(chunk_db, "indexed_filings") == 1
    assert _count(chunk_db, "chunks") == 0


def test_two_index_versions_live_side_by_side(
    store: PostgresChunkStore,
    chunk_db: str,
    read_fixture: Callable[[str], bytes],
    filing_10k: FilingRef,
    indexed: IndexedFiling,
) -> None:
    other = index_filing(read_fixture("sim-10k.htm"), filing_10k, ChunkConfig(max_tokens=400))
    assert other.index_version != indexed.index_version
    store.replace(indexed)
    store.replace(other)
    assert _count(chunk_db, "indexed_filings") == 2
    assert _count(chunk_db, "chunks") == len(indexed.chunks) + len(other.chunks)
