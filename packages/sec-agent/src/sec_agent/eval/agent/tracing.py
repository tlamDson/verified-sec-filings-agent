"""Which tool calls meet a check, and whether the shown answer states their figure.

Two ways to state the right figure:
- with the tool: a figure traced to the expected field of a matching call of the turn;
- without it (the RAG baseline offers only `search_filings`): a figure traced to a passage
  the sentence cites, whose value, unit and period the oracle call (the check's own call,
  run by the scorer) confirms. The same checker (s-10) decides both, so a correct RAG
  answer is not rejected for lacking a tool it was never given.
"""

import datetime as dt
import re
from collections.abc import Sequence

from sec_agent.agent.answer import Evidence
from sec_agent.eval.agent.scenarios import ToolCheck, matching_elements, result_values
from sec_agent.faithfulness.check import check_answer
from sec_agent.faithfulness.models import FaithfulnessReport

SEARCH_TOOL = "search_filings"


def offers(check: ToolCheck, offered: tuple[str, ...] | None) -> bool:
    """Whether a system offering `offered` could make the check's call. A check of any tool
    (`tool` None, e.g. an out-of-scope refusal) needs a tool beyond search."""
    if offered is None:
        return True
    if check.tool is None:
        return any(name != SEARCH_TOOL for name in offered)
    return check.tool in offered


def scopes(check: ToolCheck, evidence: Evidence) -> set[str]:
    """Where in this call's result a figure of the check may trace: {""} anywhere, or the
    list elements ("rows[1]") whose values match every `*` path; empty when the call does
    not match. A peer check on HD is thus met by HD's row, never by another company's."""
    if check.tool is not None and evidence.name != check.tool:
        return set()
    if evidence.ok != check.ok:
        return set()
    found = {""}
    for path, expected in check.match.items():
        if "*" in path:
            rows = matching_elements(evidence.result, path, expected)
            found = rows if found == {""} else found & rows
        elif expected not in result_values(evidence.result, path):
            return set()
        if not found:
            return set()
    return found


def matching_calls(check: ToolCheck, evidence: Sequence[Evidence]) -> dict[str, set[str]]:
    return {e.call_id: s for e in evidence if (s := scopes(check, e))}


def figure_starts(figure: str, calls: dict[str, set[str]], report: FaithfulnessReport) -> set[int]:
    """Where the answer states a figure traced to the expected field of one of `calls`."""
    pattern = re.compile(figure)
    return {
        m.mention.start
        for s in report.sentences
        for m in s.mentions
        if m.status == "traced"
        and m.source is not None
        and m.source.call_id in calls
        and pattern.fullmatch(m.source.field) is not None
        and _within(m.source.field, calls[m.source.call_id])
    }


def cited_passage_starts(report: FaithfulnessReport) -> set[int]:
    """Where the answer states a figure traced to a passage its sentence cites."""
    return {
        m.mention.start
        for s in report.sentences
        for m in s.mentions
        if m.status == "traced" and m.source is not None and m.source.citation is not None
    }


def oracle_figure_cited(
    check: ToolCheck,
    text: str,
    oracle: Sequence[Evidence],
    report: FaithfulnessReport,
    asked_on: dt.date,
) -> bool | None:
    """True when a figure of a cited passage is the oracle's; None without an oracle call."""
    assert check.figure is not None
    calls = matching_calls(check, oracle)
    if not calls:
        return None
    expected = check_answer(text, [e for e in oracle if e.call_id in calls], asked_on=asked_on)
    return bool(figure_starts(check.figure, calls, expected) & cited_passage_starts(report))


def _within(field: str, found: set[str]) -> bool:
    return "" in found or any(field.startswith(f"{scope}.") for scope in found)
