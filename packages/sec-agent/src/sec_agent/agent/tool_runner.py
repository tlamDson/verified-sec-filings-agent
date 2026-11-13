"""ToolRunner: the catalog's tools as the model sees them, and one call run to a JSON result.

The model writes a tool name and JSON arguments; this validates both, runs the tool on
the contexts pinned for the request, and returns the result as JSON text (decimals as
exact strings). A refusal is a result the model can read, never an exception. A result
over the size budget is never cut mid-text: search drops whole passages from the end,
anything else is withheld.
"""

import json
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from sec_agent.llm.messages import ToolSchema
from sec_agent.retrieval.errors import RetrievalError
from sec_agent.tools.catalog import TOOLS, ToolSpec
from sec_agent.tools.context import FactsContext, TextContext
from sec_agent.tools.errors import ToolError
from sec_agent.tools.get_fact import GetFactArgs, get_fact
from sec_agent.tools.peers import ComparePeersArgs, compare_peers
from sec_agent.tools.ratios import ComputeRatioArgs, compute_ratio
from sec_agent.tools.risk_factors import DiffRiskFactorsArgs, diff_risk_factors
from sec_agent.tools.search_filings import SearchFilingsArgs, SearchResult, search_filings

DEFAULT_MAX_RESULT_CHARS = 24_000
_TEXT_TOOLS = frozenset({"search_filings", "diff_risk_factors"})
_MAX_PROBLEMS = 5


@dataclass(frozen=True)
class ToolOutput:
    ok: bool
    content: str
    """JSON text: the tool's result, or `{"error": {"code": ..., "message": ...}}`."""
    trimmed: int = 0
    """Passages dropped from the end of a search result to fit the budget."""


def refusal(code: str, message: str) -> ToolOutput:
    return ToolOutput(False, json.dumps({"error": {"code": code, "message": message}}))


class ToolRunner:
    """Bound to one facts snapshot and, when given, one text index: build one per pinned
    `index_version`. Without a text index only the numeric tools are offered."""

    def __init__(
        self,
        facts: FactsContext,
        text: TextContext | None = None,
        *,
        max_result_chars: int = DEFAULT_MAX_RESULT_CHARS,
    ) -> None:
        if max_result_chars < 1:
            raise ValueError("max_result_chars must be positive")
        self._facts = facts
        self._text = text
        self._max_chars = max_result_chars
        self._specs: dict[str, ToolSpec] = {
            spec.name: spec for spec in TOOLS if text is not None or spec.name not in _TEXT_TOOLS
        }

    @property
    def names(self) -> tuple[str, ...]:
        """The offered tools, in catalog order."""
        return tuple(self._specs)

    def schemas(self) -> list[ToolSchema]:
        """The offered tools in the OpenAI function shape."""
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.args.model_json_schema(),
                },
            }
            for spec in self._specs.values()
        ]

    def run(self, name: str, arguments: str) -> ToolOutput:
        spec = self._specs.get(name)
        if spec is None:
            return refusal("unknown_tool", f"no such tool; the tools are: {', '.join(self._specs)}")
        try:
            args = spec.args.model_validate_json(arguments)
        except ValidationError as error:
            return refusal("invalid_arguments", _problems(error))
        try:
            result = self._call(args)
        except ToolError as error:
            return refusal(error.code, str(error))
        except RetrievalError as error:
            return refusal("search_unavailable", str(error))
        return self._fit(result)

    def _call(self, args: BaseModel) -> BaseModel:
        if isinstance(args, GetFactArgs):
            return get_fact(self._facts, args)
        if isinstance(args, ComputeRatioArgs):
            return compute_ratio(self._facts, args)
        if isinstance(args, ComparePeersArgs):
            return compare_peers(self._facts, args)
        if self._text is not None and isinstance(args, SearchFilingsArgs):
            return search_filings(self._text, args)
        if self._text is not None and isinstance(args, DiffRiskFactorsArgs):
            return diff_risk_factors(self._text, args)
        raise AssertionError(f"no tool takes {type(args).__name__}")  # the catalog grew

    def _fit(self, result: BaseModel) -> ToolOutput:
        content = result.model_dump_json()
        if len(content) <= self._max_chars:
            return ToolOutput(True, content)
        if isinstance(result, SearchResult):
            for keep in range(len(result.passages) - 1, 0, -1):
                shorter = result.model_copy(update={"passages": result.passages[:keep]})
                content = shorter.model_dump_json()
                if len(content) <= self._max_chars:
                    return ToolOutput(True, content, trimmed=len(result.passages) - keep)
        return refusal(
            "result_too_large",
            "the result is larger than one step may read; ask for less (fewer companies, "
            "a smaller k or max_changes, a narrower question)",
        )


def _problems(error: ValidationError) -> str:
    """Which argument is wrong and why, without echoing what the model sent."""
    problems = [
        f"{'.'.join(str(part) for part in e['loc']) or 'arguments'}: {e['msg']}"
        for e in error.errors(include_input=False, include_url=False)[:_MAX_PROBLEMS]
    ]
    return "; ".join(problems)
