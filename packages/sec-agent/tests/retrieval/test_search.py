"""search: dense (HNSW), BM25 and hybrid RRF in SQL, checked against exact references."""

import datetime as dt
import math
from collections import defaultdict
from typing import Any

import psycopg
import pytest
from psycopg import sql
from retrieval_corpus import CIK_A, CIK_B, OTHER_VERSION, VERSION
from retrieval_fakes import HASH_SPEC, HashEmbedder, hash_vector

from sec_agent.retrieval.build import build_index
from sec_agent.retrieval.dense import dense_sql
from sec_agent.retrieval.errors import EmbeddingMismatchError, IndexNotBuiltError
from sec_agent.retrieval.models import EmbeddingSpace, Hit, SearchFilters, SearchMode
from sec_agent.retrieval.rrf import rrf_fuse
from sec_agent.retrieval.search import BM25_B, BM25_K1, search
from sec_agent.retrieval.space import hnsw_index_name, make_space
from sec_agent.retrieval.vectors import vector_literal

Conn = psycopg.Connection[Any]
Key = tuple[str, str, int]

QUERY = "supplier interruption of simulated parts"
MODES: tuple[SearchMode, ...] = ("dense", "lexical", "hybrid")


@pytest.fixture
def space(conn: Conn, embedder: HashEmbedder) -> EmbeddingSpace:
    build_index(conn, VERSION, embedder)
    build_index(conn, OTHER_VERSION, embedder)
    return make_space(VERSION, HASH_SPEC)


def _key(hit: Hit) -> Key:
    return (hit.accession, hit.section, hit.ordinal)


def _keys(rows: list[tuple[Any, ...]]) -> list[Key]:
    return [(str(r[0]), str(r[1]), int(r[2])) for r in rows]


def _exact_dense(conn: Conn, space: EmbeddingSpace, query: str, where: str = "") -> list[Key]:
    """Brute force with every index disabled: the order the dense arm must reproduce."""
    dims = space.spec.dimensions
    qvec = vector_literal(hash_vector("query: " + query, dims), dims)
    statement = (
        "SELECT e.accession, e.section, e.ordinal FROM chunk_embeddings e"
        " JOIN chunks c USING (index_version, accession, section, ordinal)"
        f" WHERE e.space = %s {where}"
        ' ORDER BY e.embedding <=> %s::vector, e.accession COLLATE "C",'
        ' e.section COLLATE "C", e.ordinal'
    )
    with conn.transaction():
        conn.execute(b"SET LOCAL enable_indexscan = off")
        conn.execute(b"SET LOCAL enable_bitmapscan = off")
        rows = conn.execute(statement.encode(), (space.name, qvec)).fetchall()
    return _keys(rows)


def _bm25_reference(conn: Conn, version: str, query: str) -> dict[Key, float]:
    """Okapi BM25 in Python over the lexemes Postgres extracts: the lexical arm's reference."""
    docs: dict[Key, dict[str, int]] = defaultdict(dict)
    for acc, sec, ordinal, lexeme, tf in conn.execute(
        b"SELECT c.accession, c.section, c.ordinal, t.lexeme, cardinality(t.positions)"
        b" FROM chunks c, unnest(to_tsvector('english', c.text)) t WHERE c.index_version = %s",
        (version,),
    ):
        docs[(str(acc), str(sec), int(ordinal))][str(lexeme)] = int(tf)
    count = conn.execute(
        b"SELECT count(*) FROM chunks WHERE index_version = %s", (version,)
    ).fetchone()
    assert count is not None
    n = int(count[0])
    lengths = {key: sum(terms.values()) for key, terms in docs.items()}
    avg = sum(lengths.values()) / n
    terms = {
        str(r[0])
        for r in conn.execute(b"SELECT lexeme FROM unnest(to_tsvector('english', %s))", (query,))
    }
    scores: dict[Key, float] = {}
    for term in terms:
        df = sum(1 for t in docs.values() if term in t)
        if df == 0:
            continue
        idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
        for key, t in docs.items():
            if (tf := t.get(term, 0)) > 0:
                norm = tf + BM25_K1 * (1 - BM25_B + BM25_B * lengths[key] / avg)
                scores[key] = scores.get(key, 0.0) + idf * tf * (BM25_K1 + 1) / norm
    return scores


def test_dense_unfiltered_matches_exact_search(
    conn: Conn, space: EmbeddingSpace, embedder: HashEmbedder
) -> None:
    hits = search(conn, QUERY, space, embedder=embedder, mode="dense", k=8)
    assert [_key(h) for h in hits] == _exact_dense(conn, space, QUERY)[:8]
    assert [h.rank for h in hits] == list(range(1, 9))
    assert all(h.dense_rank == h.rank and h.lexical_rank is None for h in hits)
    qvec = hash_vector("query: " + QUERY, HASH_SPEC.dimensions)
    for hit in hits:
        passage = hash_vector("passage: " + hit.text, HASH_SPEC.dimensions)
        cosine = sum(a * b for a, b in zip(qvec, passage, strict=True))
        assert hit.distance == pytest.approx(1 - cosine, abs=1e-5)
        assert hit.score == pytest.approx(cosine, abs=1e-5)


def test_dense_filtered_is_exact_and_fills_k(
    conn: Conn, space: EmbeddingSpace, embedder: HashEmbedder
) -> None:
    # A selective filter must not lose results to an approximate index scan.
    filters = SearchFilters(ciks=(CIK_A,), forms=("10-Q",))
    hits = search(conn, QUERY, space, embedder=embedder, mode="dense", filters=filters, k=50)
    expected = _exact_dense(conn, space, QUERY, f"AND c.cik = '{CIK_A}' AND c.form = '10-Q'")
    assert [_key(h) for h in hits] == expected
    assert len(hits) == 3  # every 10-Q chunk


@pytest.mark.parametrize(
    ("filters", "where"),
    [
        (SearchFilters(ciks=(CIK_B,)), f"c.cik = '{CIK_B}'"),
        (SearchFilters(sections=("risk_factors", "mdna")), "c.section IN ('risk_factors', 'mdna')"),
        (SearchFilters(report_from=dt.date(2024, 1, 1)), "c.report_date >= '2024-01-01'"),
        (SearchFilters(report_to=dt.date(2024, 6, 30)), "c.report_date <= '2024-06-30'"),
    ],
)
def test_every_filter_applies_to_every_mode(
    conn: Conn,
    space: EmbeddingSpace,
    embedder: HashEmbedder,
    filters: SearchFilters,
    where: str,
) -> None:
    statement = (
        f"SELECT accession, section, ordinal FROM chunks c WHERE index_version = %s AND {where}"
    )
    allowed = set(_keys(conn.execute(statement.encode(), (VERSION,)).fetchall()))
    for mode in MODES:
        hits = search(conn, QUERY, space, embedder=embedder, mode=mode, filters=filters, k=50)
        assert hits, mode
        assert {_key(h) for h in hits} <= allowed, mode
    dense = search(conn, QUERY, space, embedder=embedder, mode="dense", filters=filters, k=50)
    assert {_key(h) for h in dense} == allowed


def test_unfiltered_dense_query_can_use_the_hnsw_index(conn: Conn, space: EmbeddingSpace) -> None:
    qvec = vector_literal(hash_vector("query: x", HASH_SPEC.dimensions), HASH_SPEC.dimensions)
    with conn.transaction():
        # The table is tiny, so make every other path look expensive: only usability counts.
        conn.execute(b"SET LOCAL enable_seqscan = off")
        conn.execute(b"SET LOCAL enable_sort = off")
        rows = conn.execute(
            sql.SQL("EXPLAIN ") + dense_sql(space, filtered=False), {"qvec": qvec, "limit": 5}
        ).fetchall()
    assert hnsw_index_name(space.name) in "\n".join(str(r[0]) for r in rows)


def test_lexical_scores_are_okapi_bm25(conn: Conn, space: EmbeddingSpace) -> None:
    hits = search(conn, QUERY, space, mode="lexical", k=100)
    reference = _bm25_reference(conn, VERSION, QUERY)
    assert {_key(h) for h in hits} == set(reference)
    for hit in hits:
        assert hit.bm25 == pytest.approx(reference[_key(hit)], rel=1e-9)
        assert hit.score == hit.bm25
        assert hit.lexical_rank == hit.rank
        assert hit.dense_rank is None
    expected = sorted(reference, key=lambda key: (-round(reference[key], 9), key))
    assert [_key(h) for h in hits] == expected


def test_lexical_mode_needs_no_embedder(conn: Conn, space: EmbeddingSpace) -> None:
    assert search(conn, "gross margin", space, mode="lexical", k=3)


@pytest.mark.parametrize(
    "query",
    ["it's \"gross\" & (margin) | !net : sales \\ 'x' <-> *", "sales:*", "margin & !"],
)
def test_query_syntax_characters_are_plain_text(
    conn: Conn, space: EmbeddingSpace, query: str
) -> None:
    assert search(conn, query, space, mode="lexical", k=5)


@pytest.mark.parametrize("query", ["the of and", "", "   ", "!!! ???"])
def test_queries_without_search_terms_find_nothing(
    conn: Conn, space: EmbeddingSpace, query: str
) -> None:
    assert search(conn, query, space, mode="lexical", k=5) == []


def test_hybrid_is_rrf_of_the_two_arms(
    conn: Conn, space: EmbeddingSpace, embedder: HashEmbedder
) -> None:
    candidates = 6
    dense = search(conn, QUERY, space, embedder=embedder, mode="dense", k=candidates)
    lexical = search(conn, QUERY, space, mode="lexical", k=candidates)
    fused = rrf_fuse([[_key(h) for h in dense], [_key(h) for h in lexical]])
    hits = search(
        conn, QUERY, space, embedder=embedder, mode="hybrid", k=len(fused), candidates=candidates
    )
    assert [(_key(h), h.score) for h in hits] == fused
    by_key = {_key(h): h for h in hits}
    for h in dense:
        assert by_key[_key(h)].dense_rank == h.rank
        assert by_key[_key(h)].distance == h.distance
    for h in lexical:
        assert by_key[_key(h)].lexical_rank == h.rank
        assert by_key[_key(h)].bm25 == h.bm25


def test_hits_carry_what_a_citation_needs(
    conn: Conn, space: EmbeddingSpace, embedder: HashEmbedder
) -> None:
    hits = search(conn, QUERY, space, embedder=embedder, k=5)
    assert len(hits) == 5
    for hit in hits:
        assert hit.index_version == VERSION
        row = conn.execute(
            b"SELECT substr(s.text, %s + 1, %s - %s), f.source_url, f.cik, f.form, f.report_date"
            b" FROM filing_sections s JOIN indexed_filings f USING (index_version, accession)"
            b" WHERE s.index_version = %s AND s.accession = %s AND s.section = %s",
            (hit.char_start, hit.char_end, hit.char_start, VERSION, hit.accession, hit.section),
        ).fetchone()
        assert row == (hit.text, hit.source_url, hit.cik, hit.form, hit.report_date)


def test_results_never_mix_index_versions(
    conn: Conn, space: EmbeddingSpace, embedder: HashEmbedder
) -> None:
    for mode in MODES:
        hits = search(conn, QUERY, space, embedder=embedder, mode=mode, k=100)
        assert {h.index_version for h in hits} == {VERSION}


def test_search_is_deterministic(conn: Conn, space: EmbeddingSpace, embedder: HashEmbedder) -> None:
    first = search(conn, QUERY, space, embedder=embedder, k=20)
    assert search(conn, QUERY, space, embedder=embedder, k=20) == first


def test_query_embedder_must_match_the_space(conn: Conn, space: EmbeddingSpace) -> None:
    other = HashEmbedder(HASH_SPEC.model_copy(update={"model": "test/other"}))
    with pytest.raises(EmbeddingMismatchError, match="test/other"):
        search(conn, QUERY, space, embedder=other, mode="hybrid")
    with pytest.raises(EmbeddingMismatchError, match="embedder"):
        search(conn, QUERY, space, mode="dense")


def test_space_that_was_never_built_is_refused(conn: Conn, embedder: HashEmbedder) -> None:
    unbuilt = make_space(VERSION, HASH_SPEC)
    for mode in MODES:
        with pytest.raises(IndexNotBuiltError):
            search(conn, QUERY, unbuilt, embedder=embedder, mode=mode)


@pytest.mark.parametrize(("k", "candidates"), [(0, 50), (5, 0), (5, 1001)])
def test_bad_sizes_are_refused(
    conn: Conn, space: EmbeddingSpace, embedder: HashEmbedder, k: int, candidates: int
) -> None:
    with pytest.raises(ValueError, match="must be"):
        search(conn, QUERY, space, embedder=embedder, k=k, candidates=candidates)
