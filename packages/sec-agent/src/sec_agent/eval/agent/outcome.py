"""Whether a shown answer delivers a text outcome: what a filing says, or how risk factors changed.

A citation alone is not an outcome: "the passages do not contain that [cite]" cites and
answers nothing. So for a check of a text tool:
- `non_answer`: a sentence of the answer says the sources (or the company) do not hold
  what was asked;
- `outcome`: no cited sentence states the outcome. For search_filings, a sentence that
  restates (`grounding`) a passage of the asked company (the check's `*` rows) it cites;
  for diff_risk_factors, a sentence claiming a change of the same kind as a paragraph the
  diff reports, and restating it (`risk_outcome`). Citations alone or a pointer ("see the
  10-K") state nothing.
Each sentence is judged by code (regexes, citation keys), never by a model.
"""

import re
from collections.abc import Sequence
from typing import Literal

from sec_agent.agent.answer import Evidence
from sec_agent.eval.agent.evidence_text import passage_texts, restates_cited
from sec_agent.eval.agent.risk_outcome import risk_diff_failure
from sec_agent.eval.agent.scenarios import ToolCheck
from sec_agent.eval.agent.tracing import matching_calls
from sec_agent.faithfulness.models import FaithfulnessReport

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
        texts = {
            k: t
            for e in source
            if e.call_id in calls
            for k, t in passage_texts(e, calls[e.call_id]).items()
        }
        return None if any(restates_cited(s, texts) for s in stated) else "outcome"
    diffs = [e for e in source if e.call_id in calls]
    return risk_diff_failure(diffs, evidence, stated, report, offered=offered)
