"""Whether a shown answer delivers a text outcome: what a filing says, or how risk factors changed.

A citation alone is not an outcome: "the passages do not contain that [cite]" cites and
answers nothing. So for a check of a text tool:
- `non_answer`: a sentence of the answer says the sources (or the company) do not hold
  what was asked;
- `outcome`: no cited sentence states the outcome. For search_filings, a sentence that
  restates (`grounding`) a passage of the asked company (the check's `*` rows) it cites;
  for diff_risk_factors, a sentence naming a change (added, removed, changed...) that cites
  a compared filing and restates a changed paragraph (with the tool) or a passage it cites
  (without). Citations alone or a pointer ("see the 10-K") state nothing. A system
  without diff_risk_factors (RAG) did the comparison itself, so its answer must cite
  passages of both filings the oracle compared.
Each sentence is judged by code (regexes, citation keys), never by a model.
"""

import re
from collections.abc import Sequence
from typing import Any, Literal, cast

from sec_agent.agent.answer import Evidence
from sec_agent.eval.agent.grounding import restates
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
        texts = {k: t for e in source if e.call_id in calls for k, t in _passages(e, calls).items()}
        return None if any(_restates_cited(s, texts) for s in stated) else "outcome"
    filings = [f for e in source if e.call_id in calls for f in _compared(e)]
    compared = {a for pair in filings for a in pair}
    changes = [t for e in source if e.call_id in calls for t in _change_texts(e)]
    passages = {k: t for e in evidence for k, t in _passages(e, {e.call_id: {""}}).items()}

    def states_change(s: SentenceCheck) -> bool:
        if _CHANGE.search(s.text) is None or not _cites_any(_cited(s), compared):
            return False
        return restates(s.text, changes) if offered else _restates_cited(s, passages)

    if not any(states_change(s) for s in stated):
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


def _restates_cited(sentence: SentenceCheck, texts: dict[str, str]) -> bool:
    """Whether the sentence restates a passage of `texts` (key -> text) that it cites."""
    return restates(sentence.text, [texts[k] for k in _cited(sentence) if k in texts])


def _passages(evidence: Evidence, calls: dict[str, set[str]]) -> dict[str, str]:
    """Citation key -> text of the passages in the call's scope (all, or the asked
    company's)."""
    scope = calls.get(evidence.call_id, set())
    found: dict[str, str] = {}
    for passages in result_values(evidence.result, "passages"):
        if not isinstance(passages, list):
            continue
        for i, passage in enumerate(cast(list[Any], passages)):
            if ("" in scope or f"passages[{i}]" in scope) and isinstance(passage, dict):
                key = cast(dict[str, Any], passage).get("citation")
                text = cast(dict[str, Any], passage).get("text")
                if isinstance(key, str) and isinstance(text, str):
                    found[key] = text
    return found


def _change_texts(evidence: Evidence) -> list[str]:
    """The paragraphs a diff reports as added, removed or changed (both sides)."""
    found = result_values(evidence.result, "changes.*.text")
    found += result_values(evidence.result, "changes.*.previous_text")
    return [t for t in found if isinstance(t, str)]


def _compared(evidence: Evidence) -> list[tuple[str, str]]:
    """The (current, previous) accessions a compared diff names."""
    current = result_values(evidence.result, "current.accession")
    previous = result_values(evidence.result, "previous.accession")
    return [(c, p) for c in current for p in previous if isinstance(c, str) and isinstance(p, str)]
