"""One MCP tool call: validate the JSON arguments, run the deterministic tool, return JSON.

The payload is the tool's own result model dumped in JSON mode, so decimals stay exact
strings and dates stay ISO dates: the server adds no number of its own. A refusal is a
payload `{"error": code, "message": text}` with a stable code.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, NamedTuple

from pydantic import BaseModel, ValidationError

from sec_agent.retrieval.errors import RetrievalError
from sec_agent.tools.catalog import TOOLS
from sec_agent.tools.context import FactsContext, TextContext
from sec_agent.tools.errors import ToolError
from sec_agent.tools.get_fact import get_fact
from sec_agent.tools.peers import compare_peers
from sec_agent.tools.ratios import compute_ratio
from sec_agent.tools.risk_factors import diff_risk_factors
from sec_agent.tools.search_filings import search_filings

_FACT_TOOLS: Mapping[str, Callable[[FactsContext, Any], BaseModel]] = {
    "get_fact": get_fact,
    "compute_ratio": compute_ratio,
    "compare_peers": compare_peers,
}
_TEXT_TOOLS: Mapping[str, Callable[[TextContext, Any], BaseModel]] = {
    "search_filings": search_filings,
    "diff_risk_factors": diff_risk_factors,
}
_SPECS = {spec.name: spec for spec in TOOLS}


@dataclass(frozen=True)
class ToolContexts:
    """What every call reads: a facts snapshot, and a text index when one is served."""

    facts: FactsContext
    text: TextContext | None = None


class CallOutcome(NamedTuple):
    is_error: bool
    payload: dict[str, Any]


def call_tool(
    contexts: ToolContexts, name: str, arguments: Mapping[str, Any] | None
) -> CallOutcome:
    spec = _SPECS.get(name)
    if spec is None:
        return _error("unknown_tool", f"no tool named {name!r}")
    try:
        args = spec.args.model_validate(dict(arguments or {}))
    except ValidationError as error:
        return _error("invalid_arguments", _summary(error))
    try:
        result = _run(contexts, name, args)
    except ToolError as error:
        return _error(error.code, str(error))
    except RetrievalError as error:
        return _error("retrieval_error", str(error))
    if result is None:
        return _error("text_index_unavailable", "this server has no filing text index loaded")
    return CallOutcome(False, result.model_dump(mode="json"))


def _run(contexts: ToolContexts, name: str, args: BaseModel) -> BaseModel | None:
    if name in _FACT_TOOLS:
        return _FACT_TOOLS[name](contexts.facts, args)
    if contexts.text is None:
        return None
    return _TEXT_TOOLS[name](contexts.text, args)


def _summary(error: ValidationError) -> str:
    """Field and reason of each problem; the rejected input itself is not echoed."""
    parts = [
        f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in error.errors()
    ]
    return "; ".join(parts)


def _error(code: str, message: str) -> CallOutcome:
    return CallOutcome(True, {"error": code, "message": message})
