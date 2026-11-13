"""ToolRunner: the catalog's tools as the model sees them, and one call run to a JSON result."""

import json
from decimal import Decimal
from typing import Any, cast

import psycopg
import pytest
from agent_kit import APPLE_REVENUE_FY2024
from retrieval_corpus import CIK_A, CIK_B, CONFIG, VERSION, store_corpus
from retrieval_fakes import HASH_SPEC, HashEmbedder

from sec_agent.agent.tool_runner import ToolRunner
from sec_agent.golden.universe import Company
from sec_agent.retrieval.build import build_index
from sec_agent.retrieval.space import make_space
from sec_agent.tools.catalog import TOOLS, tool
from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.context import FactsContext, TextContext
from sec_agent.tools.get_fact import GetFactResult
from sec_agent.tools.risk_sections import PostgresRiskSections
from sec_agent.tools.search_filings import SearchResult

APPLE_REVENUE = '{"company": "AAPL", "concept": "revenue", "fiscal_year": 2024}'


def _error(content: str) -> dict[str, str]:
    payload = json.loads(content)
    assert set(payload) == {"error"}
    return cast(dict[str, str], payload["error"])


def test_without_a_text_index_only_the_numeric_tools_are_offered(facts_ctx: FactsContext) -> None:
    schemas = ToolRunner(facts_ctx).schemas()
    assert [s["function"]["name"] for s in schemas] == [
        "get_fact",
        "compute_ratio",
        "compare_peers",
    ]


def test_schemas_are_the_catalog_in_the_openai_function_shape(facts_ctx: FactsContext) -> None:
    runner = ToolRunner(facts_ctx, cast(TextContext, object()))
    schemas = runner.schemas()
    assert [s["function"]["name"] for s in schemas] == [spec.name for spec in TOOLS]
    for schema in schemas:
        spec = tool(schema["function"]["name"])
        assert schema["type"] == "function"
        assert schema["function"]["description"] == spec.description
        assert schema["function"]["parameters"] == spec.args.model_json_schema()


def test_a_call_returns_the_tool_result_as_json_with_exact_decimals(
    facts_ctx: FactsContext,
) -> None:
    output = ToolRunner(facts_ctx).run("get_fact", APPLE_REVENUE)
    assert output.ok
    assert output.trimmed == 0
    result = GetFactResult.model_validate_json(output.content)
    assert result.fact is not None
    assert result.fact.value == Decimal(APPLE_REVENUE_FY2024)
    assert json.loads(output.content)["fact"]["value"] == APPLE_REVENUE_FY2024, "never a float"
    assert result.index_version == "x-test"


def test_a_tool_refusal_is_a_result_the_model_can_read(facts_ctx: FactsContext) -> None:
    output = ToolRunner(facts_ctx).run(
        "get_fact", '{"company": "ZZZZ", "concept": "revenue", "fiscal_year": 2024}'
    )
    assert not output.ok
    error = _error(output.content)
    assert error["code"] == "unknown_company"
    assert error["message"]


@pytest.mark.parametrize(
    "arguments",
    [
        "",
        "not json",
        "[]",
        '{"company": "AAPL"}',
        '{"company": "AAPL", "concept": "revenue", "fiscal_year": "soon"}',
        '{"company": "AAPL", "concept": "revenue", "fiscal_year": 2024, "guess": true}',
    ],
)
def test_arguments_that_do_not_fit_the_schema_are_named(
    facts_ctx: FactsContext, arguments: str
) -> None:
    output = ToolRunner(facts_ctx).run("get_fact", arguments)
    assert not output.ok
    assert _error(output.content)["code"] == "invalid_arguments"


@pytest.mark.parametrize("name", ["delete_everything", "search_filings", "diff_risk_factors"])
def test_a_tool_that_is_not_offered_cannot_be_called(facts_ctx: FactsContext, name: str) -> None:
    output = ToolRunner(facts_ctx).run(name, "{}")
    assert not output.ok
    error = _error(output.content)
    assert error["code"] == "unknown_tool"
    assert "get_fact" in error["message"]


def test_a_result_over_the_budget_is_withheld_whole_never_cut(facts_ctx: FactsContext) -> None:
    """A result cut in the middle could show the model half a number."""
    output = ToolRunner(facts_ctx, max_result_chars=200).run("get_fact", APPLE_REVENUE)
    assert not output.ok
    assert _error(output.content)["code"] == "result_too_large"
    assert APPLE_REVENUE_FY2024[:6] not in output.content


def _text_ctx(conn: psycopg.Connection[Any]) -> TextContext:
    directory = CompanyDirectory(
        [
            Company(
                ticker="SIMW", name="Simulated Widgets Inc.", sector="Industrials", cik=int(CIK_A)
            ),
            Company(ticker="SIMB", name="Simulated B Corp", sector="Industrials", cik=int(CIK_B)),
        ]
    )
    return TextContext(
        companies=directory,
        conn=conn,
        space=make_space(VERSION, HASH_SPEC),
        sections=PostgresRiskSections(conn),
        facts_version="x-test",
        embedder=HashEmbedder(),
    )


@pytest.fixture
def indexed_conn(pg_uri: str, text_conn: psycopg.Connection[Any]) -> psycopg.Connection[Any]:
    store_corpus(pg_uri, CONFIG)
    build_index(text_conn, VERSION, HashEmbedder())
    return text_conn


SEARCH = '{"query": "supplier interruption of simulated parts", "k": 6}'


def test_search_runs_on_the_pinned_text_index(
    facts_ctx: FactsContext, indexed_conn: psycopg.Connection[Any]
) -> None:
    output = ToolRunner(facts_ctx, _text_ctx(indexed_conn)).run("search_filings", SEARCH)
    assert output.ok
    result = SearchResult.model_validate_json(output.content)
    assert result.index_version == VERSION
    assert len(result.passages) == 6
    assert output.trimmed == 0


def test_search_over_the_budget_drops_whole_passages_from_the_end(
    facts_ctx: FactsContext, indexed_conn: psycopg.Connection[Any]
) -> None:
    ctx = _text_ctx(indexed_conn)
    full = SearchResult.model_validate_json(
        ToolRunner(facts_ctx, ctx).run("search_filings", SEARCH).content
    )
    budget = len(full.model_copy(update={"passages": full.passages[:3]}).model_dump_json()) + 10
    output = ToolRunner(facts_ctx, ctx, max_result_chars=budget).run("search_filings", SEARCH)
    assert output.ok
    assert len(output.content) <= budget
    kept = SearchResult.model_validate_json(output.content)
    assert kept.passages == full.passages[:3]
    assert output.trimmed == 3


def test_search_with_no_room_for_one_passage_is_withheld(
    facts_ctx: FactsContext, indexed_conn: psycopg.Connection[Any]
) -> None:
    output = ToolRunner(facts_ctx, _text_ctx(indexed_conn), max_result_chars=300).run(
        "search_filings", SEARCH
    )
    assert not output.ok
    assert _error(output.content)["code"] == "result_too_large"
