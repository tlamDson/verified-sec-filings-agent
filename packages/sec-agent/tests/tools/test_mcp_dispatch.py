"""MCP dispatch: a tool name and JSON arguments in, the tool's JSON result or a coded error out.

Facts are the recorded Apple and NVIDIA companyfacts; no network, no database.
"""

from typing import Any

import pytest

from sec_agent.mcp_server.dispatch import ToolContexts, call_tool
from sec_agent.tools.context import FactsContext


def _ok(ctx: FactsContext, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    outcome = call_tool(ToolContexts(facts=ctx), name, arguments)
    assert not outcome.is_error, outcome.payload
    return outcome.payload


def _error(ctx: FactsContext, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    outcome = call_tool(ToolContexts(facts=ctx), name, arguments)
    assert outcome.is_error, outcome.payload
    assert set(outcome.payload) == {"error", "message"}
    return outcome.payload


def test_get_fact_returns_the_json_result_with_exact_value(facts_ctx: FactsContext) -> None:
    payload = _ok(facts_ctx, "get_fact", {"company": "AAPL", "concept": "revenue", "fiscal_year": 2024})
    assert payload["status"] == "found"
    fact = payload["fact"]
    assert fact["value"] == "391035000000"  # a decimal string: never rounded through a float
    assert fact["period_end"] == "2024-09-28"
    assert fact["accession"] == "0000320193-25-000079"
    assert payload["index_version"] == "x-test"


def test_compute_ratio_and_compare_peers_dispatch(facts_ctx: FactsContext) -> None:
    ratio = _ok(
        facts_ctx, "compute_ratio", {"company": "AAPL", "ratio": "gross_margin", "fiscal_year": 2024}
    )
    assert ratio["value"] == "46.206350"
    peers = _ok(
        facts_ctx,
        "compare_peers",
        {"companies": ["AAPL", "NVDA"], "metric": "revenue", "fiscal_year": 2024},
    )
    assert {r["company"]["ticker"] for r in peers["rows"]} == {"AAPL", "NVDA"}


def test_json_lists_and_numeric_strings_are_accepted(facts_ctx: FactsContext) -> None:
    payload = _ok(
        facts_ctx, "get_fact", {"company": "AAPL", "concept": "revenue", "fiscal_year": "2024"}
    )
    assert payload["fiscal_year"] == 2024


def test_not_reported_is_a_result_not_an_error(facts_ctx: FactsContext) -> None:
    payload = _ok(facts_ctx, "get_fact", {"company": "AAPL", "concept": "revenue", "fiscal_year": 2030})
    assert payload["status"] == "not_reported"
    assert payload["fact"] is None


@pytest.mark.parametrize(
    ("arguments", "code"),
    [
        ({"company": "TINYCO", "concept": "revenue", "fiscal_year": 2024}, "unknown_company"),
        ({"company": "AAPL", "concept": "adjusted_ebitda", "fiscal_year": 2024}, "unknown_metric"),
    ],
)
def test_tool_errors_keep_their_code(
    facts_ctx: FactsContext, arguments: dict[str, Any], code: str
) -> None:
    payload = _error(facts_ctx, "get_fact", arguments)
    assert payload["error"] == code
    assert payload["message"]


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        {"company": "AAPL", "concept": "revenue"},
        {"company": "AAPL", "concept": "revenue", "fiscal_year": 2024, "extra": 1},
        {"company": "AAPL", "concept": "revenue", "fiscal_year": 2024, "fiscal_period": "Q9"},
    ],
)
def test_bad_arguments_are_invalid_arguments(
    facts_ctx: FactsContext, arguments: dict[str, Any] | None
) -> None:
    payload = _error(facts_ctx, "get_fact", arguments)
    assert payload["error"] == "invalid_arguments"


def test_invalid_arguments_message_names_the_field(facts_ctx: FactsContext) -> None:
    payload = _error(facts_ctx, "get_fact", {"company": "AAPL", "concept": "revenue"})
    assert "fiscal_year" in payload["message"]


def test_unknown_tool(facts_ctx: FactsContext) -> None:
    payload = _error(facts_ctx, "buy_stock", {})
    assert payload["error"] == "unknown_tool"


@pytest.mark.parametrize("name", ["search_filings", "diff_risk_factors"])
def test_text_tools_without_a_text_index_say_so(facts_ctx: FactsContext, name: str) -> None:
    arguments = {"query": "supply"} if name == "search_filings" else {"company": "AAPL"}
    payload = _error(facts_ctx, name, arguments)
    assert payload["error"] == "text_index_unavailable"
