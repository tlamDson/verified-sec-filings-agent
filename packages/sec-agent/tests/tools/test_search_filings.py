"""search_filings: hybrid retrieval over the pinned space, returned as citable passages.

The corpus is the simulated one the retrieval tests share (`retrieval_corpus`).
"""

import datetime as dt
from typing import Any

import psycopg
import pytest
from pydantic import ValidationError
from retrieval_corpus import CIK_A, CIK_B, CONFIG, VERSION, store_corpus
from retrieval_fakes import HASH_SPEC, HashEmbedder

from sec_agent.golden.universe import Company
from sec_agent.retrieval.build import build_index
from sec_agent.retrieval.models import SearchFilters
from sec_agent.retrieval.search import search
from sec_agent.retrieval.space import make_space
from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.context import TextContext
from sec_agent.tools.errors import UnknownCompanyError
from sec_agent.tools.risk_sections import PostgresRiskSections
from sec_agent.tools.search_filings import SearchFilingsArgs, search_filings

QUERY = "supplier interruption of simulated parts"

DIRECTORY = CompanyDirectory(
    [
        Company(ticker="SIMW", name="Simulated Widgets Inc.", sector="Industrials", cik=int(CIK_A)),
        Company(ticker="SIMB", name="Simulated B Corp", sector="Industrials", cik=int(CIK_B)),
    ]
)


def _ctx(conn: psycopg.Connection[Any], embedder: HashEmbedder | None) -> TextContext:
    return TextContext(
        companies=DIRECTORY,
        conn=conn,
        space=make_space(VERSION, HASH_SPEC),
        sections=PostgresRiskSections(conn),
        facts_version="x-test",
        embedder=embedder,
    )


@pytest.fixture
def indexed_conn(tools_db: str, tools_conn: psycopg.Connection[Any]) -> psycopg.Connection[Any]:
    store_corpus(tools_db, CONFIG)
    build_index(tools_conn, VERSION, HashEmbedder())
    return tools_conn


def test_passages_are_the_hybrid_hits_with_citations(
    indexed_conn: psycopg.Connection[Any],
) -> None:
    embedder = HashEmbedder()
    ctx = _ctx(indexed_conn, embedder)
    result = search_filings(ctx, SearchFilingsArgs(query=QUERY, k=5))
    hits = search(indexed_conn, QUERY, ctx.space, embedder=embedder, mode="hybrid", k=5)
    assert result.mode == "hybrid"
    assert result.index_version == VERSION
    assert result.space == ctx.space.name
    assert [(p.accession, p.section, p.ordinal) for p in result.passages] == [
        (h.accession, h.section, h.ordinal) for h in hits
    ]
    first = result.passages[0]
    assert first.rank == 1
    assert first.citation == f"{first.accession}/{first.section}/{first.ordinal}"
    assert first.source_url.startswith("https://www.sec.gov/Archives/edgar/data/")
    assert first.char_end > first.char_start
    assert first.company is not None
    assert first.company.ticker in {"SIMW", "SIMB"}


def test_company_and_form_filters(indexed_conn: psycopg.Connection[Any]) -> None:
    ctx = _ctx(indexed_conn, HashEmbedder())
    result = search_filings(
        ctx, SearchFilingsArgs(query=QUERY, companies=("simw",), forms=("10-Q",), k=10)
    )
    assert result.passages
    assert {(p.cik, p.form) for p in result.passages} == {(CIK_A, "10-Q")}
    assert result.filters == SearchFilters(ciks=(CIK_A,), forms=("10-Q",))


def test_report_date_and_section_filters(indexed_conn: psycopg.Connection[Any]) -> None:
    ctx = _ctx(indexed_conn, HashEmbedder())
    args = SearchFilingsArgs(
        query=QUERY,
        sections=("risk_factors",),
        report_from=dt.date(2024, 1, 1),
        report_to=dt.date(2024, 12, 31),
    )
    result = search_filings(ctx, args)
    assert result.passages
    assert {p.section for p in result.passages} == {"risk_factors"}
    assert all(
        dt.date(2024, 1, 1) <= p.report_date <= dt.date(2024, 12, 31) for p in result.passages
    )


def test_without_an_embedder_the_search_is_lexical(indexed_conn: psycopg.Connection[Any]) -> None:
    ctx = _ctx(indexed_conn, None)
    result = search_filings(ctx, SearchFilingsArgs(query=QUERY, k=3))
    hits = search(indexed_conn, QUERY, ctx.space, mode="lexical", k=3)
    assert result.mode == "lexical"
    assert [p.citation for p in result.passages] == [
        f"{h.accession}/{h.section}/{h.ordinal}" for h in hits
    ]


def test_an_unknown_company_filter_is_refused(indexed_conn: psycopg.Connection[Any]) -> None:
    with pytest.raises(UnknownCompanyError):
        search_filings(
            _ctx(indexed_conn, HashEmbedder()), SearchFilingsArgs(query=QUERY, companies=("AAPL",))
        )


@pytest.mark.parametrize(
    "bad",
    [
        {"query": ""},
        {"query": "x" * 1001},
        {"query": "ok", "k": 0},
        {"query": "ok", "k": 21},
        {"query": "ok", "forms": ("8-K",)},
        {"query": "ok", "companies": tuple(f"T{i}" for i in range(11))},
    ],
)
def test_arguments_are_validated(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SearchFilingsArgs.model_validate(bad)
