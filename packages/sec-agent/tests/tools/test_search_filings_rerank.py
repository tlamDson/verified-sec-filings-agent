"""search_filings with a reranker: hybrid candidates reordered, or the hybrid order kept
when the reranker fails (failure mode "reranker slow or down")."""

from typing import Any

import psycopg
import pytest
from rerank_kit import BlockingScorer, BrokenScorer, FakeScorer, by_length
from retrieval_corpus import CIK_A, CIK_B, CONFIG, VERSION, store_corpus
from retrieval_fakes import HASH_SPEC, HashEmbedder

from sec_agent.golden.universe import Company
from sec_agent.llm.breaker import BreakerConfig
from sec_agent.retrieval.build import build_index
from sec_agent.retrieval.search import search
from sec_agent.retrieval.space import make_space
from sec_agent.rerank.service import RerankConfig, Reranker
from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.context import TextContext
from sec_agent.tools.risk_sections import PostgresRiskSections
from sec_agent.tools.search_filings import SearchFilingsArgs, search_filings

QUERY = "supplier interruption of simulated parts"
DIRECTORY = CompanyDirectory(
    [
        Company(ticker="SIMW", name="Simulated Widgets Inc.", sector="Industrials", cik=int(CIK_A)),
        Company(ticker="SIMB", name="Simulated B Corp", sector="Industrials", cik=int(CIK_B)),
    ]
)
CONFIG_FAST = RerankConfig(
    depth=6, timeout_seconds=0.05, breaker=BreakerConfig(failure_threshold=5)
)


def _ctx(conn: psycopg.Connection[Any], scorer: object) -> TextContext:
    return TextContext(
        companies=DIRECTORY,
        conn=conn,
        space=make_space(VERSION, HASH_SPEC),
        sections=PostgresRiskSections(conn),
        facts_version="x-test",
        embedder=HashEmbedder(),
        reranker=Reranker(scorer, CONFIG_FAST),  # pyright: ignore[reportArgumentType]
    )


@pytest.fixture
def indexed_conn(tools_db: str, tools_conn: psycopg.Connection[Any]) -> psycopg.Connection[Any]:
    store_corpus(tools_db, CONFIG)
    build_index(tools_conn, VERSION, HashEmbedder())
    return tools_conn


def _hybrid(conn: psycopg.Connection[Any], ctx: TextContext, k: int) -> list[str]:
    hits = search(conn, QUERY, ctx.space, embedder=HashEmbedder(), mode="hybrid", k=k)
    return [f"{h.accession}/{h.section}/{h.ordinal}" for h in hits]


def test_the_reranker_reorders_the_hybrid_candidates(
    indexed_conn: psycopg.Connection[Any],
) -> None:
    scorer = FakeScorer(by_length, name="len-reranker")
    ctx = _ctx(indexed_conn, scorer)
    result = search_filings(ctx, SearchFilingsArgs(query=QUERY, k=3))
    candidates = _hybrid(indexed_conn, ctx, 6)
    [(query, texts)] = scorer.calls
    assert query == QUERY
    assert len(texts) == len(candidates)
    by_citation = dict(zip(candidates, texts, strict=True))
    expected = sorted(candidates, key=lambda c: (-len(by_citation[c]), candidates.index(c)))[:3]
    assert [p.citation for p in result.passages] == expected
    assert [p.rank for p in result.passages] == [1, 2, 3]
    assert [p.rerank_score for p in result.passages] == [
        float(len(by_citation[c])) for c in expected
    ]
    assert result.reranker == "len-reranker"
    assert result.rerank_fallback is None


def test_a_broken_reranker_keeps_the_hybrid_order(indexed_conn: psycopg.Connection[Any]) -> None:
    ctx = _ctx(indexed_conn, BrokenScorer())
    result = search_filings(ctx, SearchFilingsArgs(query=QUERY, k=3))
    assert [p.citation for p in result.passages] == _hybrid(indexed_conn, ctx, 3)
    assert all(p.rerank_score is None for p in result.passages)
    assert result.reranker is None
    assert result.rerank_fallback == "error"


def test_a_slow_reranker_keeps_the_hybrid_order(indexed_conn: psycopg.Connection[Any]) -> None:
    scorer = BlockingScorer()
    ctx = _ctx(indexed_conn, scorer)
    try:
        result = search_filings(ctx, SearchFilingsArgs(query=QUERY, k=3))
    finally:
        scorer.release.set()
    assert [p.citation for p in result.passages] == _hybrid(indexed_conn, ctx, 3)
    assert result.rerank_fallback == "timeout"


def test_without_a_reranker_nothing_is_reranked(indexed_conn: psycopg.Connection[Any]) -> None:
    ctx = TextContext(
        companies=DIRECTORY,
        conn=indexed_conn,
        space=make_space(VERSION, HASH_SPEC),
        sections=PostgresRiskSections(indexed_conn),
        facts_version="x-test",
        embedder=HashEmbedder(),
    )
    result = search_filings(ctx, SearchFilingsArgs(query=QUERY, k=3))
    assert result.reranker is None
    assert result.rerank_fallback is None
    assert [p.citation for p in result.passages] == _hybrid(indexed_conn, ctx, 3)
