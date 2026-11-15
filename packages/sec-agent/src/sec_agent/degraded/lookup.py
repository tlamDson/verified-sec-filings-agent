"""deterministic_evidence: run the tools a question calls for, with no model in the loop.

The question is read by rules (`question`), then the same tools the agent uses are run
through the same runner, so each result is evidence exactly like the agent's. Without a
fiscal year in the question, the latest reported one is found by asking for the year of
the question's date and stepping back (E6): the card states the period it shows. The
number of tool calls is bounded, and nothing is looked up for a question that names no
company, apart from a text search when a text index is served.
"""

import datetime as dt
import json
from typing import Any, Protocol

from sec_agent.agent.answer import Evidence
from sec_agent.agent.tool_runner import ToolOutput
from sec_agent.degraded.lexicon import Metric
from sec_agent.degraded.question import QuestionParts, read_question
from sec_agent.tools.companies import CompanyDirectory, CompanyRef
from sec_agent.tools.ratio_defs import GROWTH
from sec_agent.tools.search_filings import MAX_QUERY_CHARS

MAX_CALLS = 16
PROBE_YEARS = 4
"""Fiscal years tried for "the latest reported": the question's year and three before."""
SEARCH_PASSAGES = 5
RISK_CHANGES = 10
DEFAULT_METRICS = (Metric("concept", "revenue"), Metric("concept", "net_income"))
"""Shown for a company when the question names no figure and no text can be searched."""
_REPORTED = frozenset({"found", "computed"})


class Tools(Protocol):
    @property
    def names(self) -> tuple[str, ...]: ...

    def run(self, name: str, arguments: str) -> ToolOutput: ...


def deterministic_evidence(
    question: str, *, tools: Tools, companies: CompanyDirectory, asked_on: dt.date
) -> tuple[Evidence, ...]:
    parts = read_question(question, companies)
    text_search = "search_filings" in tools.names
    risk_diff = parts.risk_changes and bool(parts.companies) and "diff_risk_factors" in tools.names
    run = _Lookups(tools, budget=MAX_CALLS - text_search - risk_diff)
    metrics = parts.metrics or (() if text_search else DEFAULT_METRICS)
    if parts.companies and metrics:
        _figures(run, parts, metrics, asked_on.year)
    run.budget += text_search + risk_diff
    if risk_diff:
        run.keep("diff_risk_factors", company=parts.companies[0].ticker, max_changes=RISK_CHANGES)
    if text_search:
        tickers = [c.ticker for c in parts.companies]
        scope: dict[str, Any] = {"companies": tickers} if tickers else {}
        run.keep(
            "search_filings", query=question.strip()[:MAX_QUERY_CHARS], **scope, k=SEARCH_PASSAGES
        )
    return run.evidence()


def _figures(run: "_Lookups", parts: QuestionParts, metrics: tuple[Metric, ...], year: int) -> None:
    several = len(parts.companies) > 1
    if several and parts.span is None and len(parts.years) <= 1:
        years = _years(run, parts, parts.companies[0], metrics[0], year)
        tickers = [c.ticker for c in parts.companies]
        for metric in metrics:
            run.keep(
                "compare_peers", **_peer_arguments(parts, metric, years[-1], companies=tickers)
            )
        return
    for company in parts.companies:
        years = _years(run, parts, company, metrics[0], year)
        for metric in metrics:
            for fiscal_year in years:
                name, arguments = _lookup(company, metric, fiscal_year, parts)
                run.keep(name, **arguments)
                if parts.growth and metric.kind == "concept":
                    run.keep("compute_ratio", **_growth(company, metric, fiscal_year, parts))
        if parts.peers and not several:
            for metric in metrics:
                peers = _peer_arguments(parts, metric, years[-1], peers_of=company.ticker)
                run.keep("compare_peers", **peers)


def _years(
    run: "_Lookups", parts: QuestionParts, company: CompanyRef, metric: Metric, year: int
) -> tuple[int, ...]:
    """The fiscal years to show: those written, or the latest reported one, or the span
    ending at it."""
    if parts.years:
        return parts.years
    latest = year
    for candidate in range(year, year - PROBE_YEARS, -1):
        name, arguments = _lookup(company, metric, candidate, parts)
        if run.reported(name, **arguments):
            latest = candidate
            break
    return tuple(range(latest - (parts.span or 1) + 1, latest + 1))


def _lookup(
    company: CompanyRef, metric: Metric, fiscal_year: int, parts: QuestionParts
) -> tuple[str, dict[str, Any]]:
    period = {"fiscal_year": fiscal_year, "fiscal_period": parts.fiscal_period}
    if metric.kind == "concept":
        return "get_fact", {"company": company.ticker, "concept": metric.name, **period}
    return "compute_ratio", {"company": company.ticker, "ratio": metric.name, **period}


def _growth(
    company: CompanyRef, metric: Metric, fiscal_year: int, parts: QuestionParts
) -> dict[str, Any]:
    return {
        "company": company.ticker,
        "ratio": GROWTH,
        "concept": metric.name,
        "fiscal_year": fiscal_year,
        "fiscal_period": parts.fiscal_period,
    }


def _peer_arguments(
    parts: QuestionParts, metric: Metric, fiscal_year: int, **who: Any
) -> dict[str, Any]:
    return {
        **who,
        "metric": metric.name,
        "fiscal_year": fiscal_year,
        "fiscal_period": parts.fiscal_period,
    }


class _Lookups:
    """Tool calls within a budget. A call is run once however often it is asked for; only
    the calls kept become evidence, in the order kept."""

    def __init__(self, tools: Tools, budget: int) -> None:
        self._tools = tools
        self.budget = budget
        self._outputs: dict[tuple[str, str], ToolOutput] = {}
        self._kept: list[tuple[str, str]] = []

    def reported(self, name: str, **arguments: Any) -> bool:
        """Whether the call returned a value; False too when the budget is spent."""
        output = self._run(name, json.dumps(arguments))
        if output is None or not output.ok:
            return False
        status: object = json.loads(output.content).get("status")
        return status in _REPORTED

    def keep(self, name: str, **arguments: Any) -> None:
        key = (name, json.dumps(arguments))
        if self._run(*key) is not None and key not in self._kept:
            self._kept.append(key)

    def evidence(self) -> tuple[Evidence, ...]:
        return tuple(
            Evidence(
                call_id=f"d{number}",
                name=name,
                arguments=arguments,
                result=self._outputs[name, arguments].content,
                ok=self._outputs[name, arguments].ok,
                trimmed=self._outputs[name, arguments].trimmed,
            )
            for number, (name, arguments) in enumerate(self._kept, start=1)
        )

    def _run(self, name: str, arguments: str) -> ToolOutput | None:
        key = (name, arguments)
        if key not in self._outputs:
            if self.budget < 1:
                return None
            self.budget -= 1
            self._outputs[key] = self._tools.run(name, arguments)
        return self._outputs[key]
