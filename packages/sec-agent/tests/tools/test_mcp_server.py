"""The MCP server, driven by an in-process MCP client: list the five tools, call each one.

Facts are the recorded Apple and NVIDIA companyfacts. Filing text, companies and risk
factor paragraphs named SIM... are simulated. No network: the client runs in-process.
"""

import datetime as dt
import json
from typing import Any

import mcp_types as types
import psycopg
import pytest
from mcp import Client
from retrieval_corpus import CIK_A, CIK_B, CONFIG, VERSION, store_corpus
from retrieval_fakes import HASH_SPEC, HashEmbedder

from sec_agent.golden.universe import Company
from sec_agent.mcp_server.dispatch import ToolContexts
from sec_agent.mcp_server.server import build_server, tool_definitions
from sec_agent.retrieval.build import build_index
from sec_agent.retrieval.space import make_space
from sec_agent.tools.catalog import TOOLS
from sec_agent.tools.companies import CompanyDirectory
from sec_agent.tools.context import FactsContext, TextContext
from sec_agent.tools.risk_sections import RiskSection

pytestmark = pytest.mark.anyio

SIM_DIRECTORY = CompanyDirectory(
    [
        Company(ticker="SIMW", name="Simulated Widgets Inc.", sector="Industrials", cik=int(CIK_A)),
        Company(ticker="SIMB", name="Simulated B Corp", sector="Industrials", cik=int(CIK_B)),
    ]
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _SimSections:
    """Two simulated 10-K risk factor sections of SIMW, fiscal 2023 and 2024."""

    def annual_risk_sections(
        self, *, cik: int, text_version: str, facts_version: str
    ) -> list[RiskSection]:
        if cik != int(CIK_A):
            return []
        return [
            _section(1, 2023, "Supply of simulated parts may be interrupted."),
            _section(
                2,
                2024,
                "Supply of simulated parts may be interrupted.\n"
                "New simulated export controls may restrict sales.",
            ),
        ]


def _section(n: int, year: int, text: str) -> RiskSection:
    return RiskSection(
        accession=f"{CIK_A}-{year % 100}-{n:06d}",
        form="10-K",
        filing_date=dt.date(year + 1, 2, 1),
        report_date=dt.date(year, 12, 31),
        source_url=f"https://www.sec.gov/Archives/edgar/data/sim/{n}.htm",
        text=text,
        xbrl_fiscal_year=year,
    )


def _payload(result: types.CallToolResult) -> dict[str, Any]:
    assert len(result.content) == 1
    block = result.content[0]
    assert isinstance(block, types.TextContent)
    payload: dict[str, Any] = json.loads(block.text)
    return payload


async def test_lists_the_five_catalog_tools_with_their_schemas(facts_ctx: FactsContext) -> None:
    async with Client(build_server(ToolContexts(facts=facts_ctx))) as client:
        listed = await client.list_tools()
    assert [t.name for t in listed.tools] == [t.name for t in TOOLS]
    for spec, listed_tool in zip(TOOLS, listed.tools, strict=True):
        assert listed_tool.description == spec.description
        assert listed_tool.input_schema == spec.args.model_json_schema()
        assert listed_tool.output_schema == spec.result.model_json_schema(mode="serialization")
        annotations = listed_tool.annotations
        assert annotations is not None
        assert annotations.read_only_hint is True
        assert annotations.destructive_hint is False
        assert annotations.open_world_hint is False


def test_tool_definitions_match_what_the_server_lists() -> None:
    assert [t.name for t in tool_definitions()] == [t.name for t in TOOLS]


async def test_server_tells_the_client_numbers_come_from_tools(facts_ctx: FactsContext) -> None:
    async with Client(build_server(ToolContexts(facts=facts_ctx))) as client:
        instructions = client.instructions
    assert instructions is not None
    assert "number" in instructions
    assert "investment advice" in instructions


async def test_get_fact_returns_structured_and_text_content(facts_ctx: FactsContext) -> None:
    async with Client(build_server(ToolContexts(facts=facts_ctx))) as client:
        result = await client.call_tool(
            "get_fact", {"company": "NVDA", "concept": "revenue", "fiscal_year": 2024}
        )
    assert result.is_error is False
    payload = _payload(result)
    assert result.structured_content == payload
    assert payload["fact"]["period_end"] == "2024-01-28"  # NVIDIA's fiscal 2024 (E1)
    assert payload["fact"]["unit"] == "USD"


async def test_a_refusal_is_an_error_result(facts_ctx: FactsContext) -> None:
    async with Client(build_server(ToolContexts(facts=facts_ctx))) as client:
        result = await client.call_tool(
            "get_fact", {"company": "TINYCO", "concept": "revenue", "fiscal_year": 2024}
        )
    assert result.is_error is True
    assert result.structured_content is None
    assert _payload(result)["error"] == "unknown_company"


@pytest.fixture
def text_ctx(tools_db: str, tools_conn: psycopg.Connection[Any]) -> TextContext:
    store_corpus(tools_db, CONFIG)
    build_index(tools_conn, VERSION, HashEmbedder())
    return TextContext(
        companies=SIM_DIRECTORY,
        conn=tools_conn,
        space=make_space(VERSION, HASH_SPEC),
        sections=_SimSections(),
        facts_version="x-test",
        embedder=HashEmbedder(),
    )


async def test_search_filings_passages_carry_citations(
    facts_ctx: FactsContext, text_ctx: TextContext
) -> None:
    async with Client(build_server(ToolContexts(facts=facts_ctx, text=text_ctx))) as client:
        result = await client.call_tool(
            "search_filings", {"query": "supplier interruption of simulated parts", "k": 3}
        )
    assert result.is_error is False
    payload = _payload(result)
    assert payload["mode"] == "hybrid"
    passages = payload["passages"]
    assert 1 <= len(passages) <= 3
    for p in passages:
        assert p["citation"] == f"{p['accession']}/{p['section']}/{p['ordinal']}"
        assert p["text"]


async def test_diff_risk_factors_through_the_server(
    facts_ctx: FactsContext, text_ctx: TextContext
) -> None:
    async with Client(build_server(ToolContexts(facts=facts_ctx, text=text_ctx))) as client:
        result = await client.call_tool("diff_risk_factors", {"company": "SIMW"})
    assert result.is_error is False
    payload = _payload(result)
    assert payload["status"] == "compared"
    assert (payload["current"]["fiscal_year"], payload["previous"]["fiscal_year"]) == (2024, 2023)
    assert [c["kind"] for c in payload["changes"]] == ["added"]
