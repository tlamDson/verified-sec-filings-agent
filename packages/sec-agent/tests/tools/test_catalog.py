"""The tool catalog: the five tools, each with a description and JSON schemas for its I/O."""

import json

from sec_agent.tools.catalog import TOOLS, tool
from sec_agent.tools.ratio_defs import GROWTH, RATIOS


def test_catalog_holds_the_five_tools() -> None:
    assert [t.name for t in TOOLS] == [
        "get_fact",
        "compute_ratio",
        "compare_peers",
        "search_filings",
        "diff_risk_factors",
    ]


def test_every_tool_describes_itself_and_has_json_schemas() -> None:
    for t in TOOLS:
        assert len(t.description) > 40, t.name
        args = t.args.model_json_schema()
        result = t.result.model_json_schema()
        assert args["type"] == "object"
        assert args.get("additionalProperties") is False, t.name
        json.dumps(args)
        json.dumps(result)


def test_get_fact_schema_lists_concepts_and_periods() -> None:
    schema = json.dumps(tool("get_fact").args.model_json_schema())
    assert "revenue" in tool("get_fact").description
    assert '"Q4"' in schema


def test_compute_ratio_description_lists_every_ratio() -> None:
    text = tool("compute_ratio").description
    for name in [*RATIOS, GROWTH]:
        assert name in text
