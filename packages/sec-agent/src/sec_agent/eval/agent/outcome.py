"""Whether a shown answer delivers a text outcome: what a filing says, or how risk factors changed.

A citation alone is not an outcome: "the passages do not contain that [cite]" cites and
answers nothing. So for a check of a text tool:
- `non_answer`: a sentence of the answer says the sources (or the company) do not hold
  what was asked;
- `outcome`: no cited sentence states the outcome. For search_filings, a sentence citing a
  passage of the asked company (the check's `*` rows); for diff_risk_factors, a sentence
  naming a change (added, removed, changed...) that cites a compared filing. A system
  without diff_risk_factors (RAG) did the comparison itself, so its answer must cite
  passages of both filings the oracle compared.
Each sentence is judged by code (regexes, citation keys), never by a model.
"""

import re
from collections.abc import Sequence
from typing import Any, Literal, cast

from sec_agent.agent.answer import Evidence
from sec_agent.eval.agent.scenarios import ToolCheck, result_values
from sec_agent.eval.agent.tracing import matching_calls
from sec_agent.faithfulness.models import FaithfulnessReport, SentenceCheck

SEARCH, DIFF = "search_filings", "diff_risk_factors"
TEXT_TOOLS = frozenset({SEARCH, DIFF})
OutcomeFailure = Literal["tool", "outcome", "oracle"]

_LACK = (
    r"(?:contain|include|provide|mention|discuss|describe|address|cover|specify|list|detail"
    r"|state|say)"
)
_NON_ANSWER = re.compile(
    r"\b(?:passages?|filings?|documents?|sources?|excerpts?|context|search results?"
    r"|(?:provided|retrieved) (?:text|information))\b"
    rf"[^.]*?\b(?:do|does|did)\s*(?:not|n't)\s+{_LACK}"
    r"|\b(?:do|does|did)\s*(?:not|n't)\s+(?:describe|discuss|mention|address)\b"
    r"|\bno (?:information|mention|details?|discussion)\b"
    r"|\b(?:cannot|can't|could not|couldn't|unable to)\s+(?:find|locate|determine|identify"
    r"|answer|confirm|compare)\b"
    r"|\bnot (?:found|available|included|present) in\b",
    re.IGNORECASE,
)
_CHANGE = re.compile(
    r"\b(?:add(?:s|ed|ing)?|new(?:ly)?|introduc\w+|remov\w+|delet\w+|dropp\w+|no longer"
    r"|chang\w+|revis\w+|updat\w+|modif\w+|expand\w+|unchanged)\b",
    re.IGNORECASE,
)


def needs_outcome(check: ToolCheck) -> bool:
    return check.ok and check.tool in TEXT_TOOLS


def is_non_answer(report: FaithfulnessReport) -> bool:
    return any(_NON_ANSWER.search(s.text) is not None for s in report.sentences)


def outcome_failure(
    check: ToolCheck,
    evidence: Sequence[Evidence],
    oracle: Sequence[Evidence],
    report: FaithfulnessReport,
    *,
    offered: bool,
) -> OutcomeFailure | None:
    """`evidence`: the turn's calls; `offered`: whether the system could call `check.tool`
    (when it could not, the check is judged against the oracle's run of `check.call`)."""
    source = evidence if offered else oracle
    calls = matching_calls(check, source)
    if not calls:
        return "tool" if offered else "oracle"
    stated = [s for s in report.sentences if _NON_ANSWER.search(s.text) is None]
    if check.tool == SEARCH:
        keys = {k for e in source if e.call_id in calls for k in _passage_keys(e, calls)}
        return None if any(_cited(s) & keys for s in stated) else "outcome"
    filings = [f for e in source if e.call_id in calls for f in _compared(e)]
    if not any(
        _CHANGE.search(s.text) and _cites_any(_cited(s), {a for pair in filings for a in pair})
        for s in stated
    ):
        return "outcome"
    if offered:
        return None
    cited = {k for s in report.sentences for k in _cited(s)}
    both = any(all(_cites_any(cited, {a}) for a in pair) for pair in filings)
    return None if both else "outcome"


def _cited(sentence: SentenceCheck) -> set[str]:
    return {c.key for c in sentence.citations if c.status == "valid"}


def _cites_any(keys: set[str], accessions: set[str]) -> bool:
    return any(k.split("/", 1)[0] in accessions for k in keys)


def _passage_keys(evidence: Evidence, calls: dict[str, set[str]]) -> set[str]:
    """Citation keys of the passages in the call's scope (all, or the asked company's)."""
    scope = calls[evidence.call_id]
    found: set[str] = set()
    for passages in result_values(evidence.result, "passages"):
        if not isinstance(passages, list):
            continue
        for i, passage in enumerate(cast(list[Any], passages)):
            if ("" in scope or f"passages[{i}]" in scope) and isinstance(passage, dict):
                key = cast(dict[str, Any], passage).get("citation")
                if isinstance(key, str):
                    found.add(key)
    return found


def _compared(evidence: Evidence) -> list[tuple[str, str]]:
    """The (current, previous) accessions a compared diff names."""
    current = result_values(evidence.result, "current.accession")
    previous = result_values(evidence.result, "previous.accession")
    return [(c, p) for c in current for p in previous if isinstance(c, str) and isinstance(p, str)]
