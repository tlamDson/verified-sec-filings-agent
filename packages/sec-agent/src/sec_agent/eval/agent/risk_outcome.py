"""Whether a shown answer states how a company's risk factors changed, as the diff says.

A sentence states a change when it cites a compared filing, claims a kind of change (added,
removed or changed) and restates (`grounding`) a paragraph the diff reports with that same
kind. So "the supplier risk was unchanged [cite]" never meets an added paragraph, and
"removed" never meets an added one. A sentence saying a risk stayed the same claims no
change at all; it is the answer only when the diff reports no change. With the tool, the
paragraphs are the system's own diff calls; without it (RAG), the oracle's diff, run with
every change (`max_changes` 200), and the sentence must also restate a passage it cites.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

from sec_agent.agent.answer import Evidence
from sec_agent.eval.agent.evidence_text import cited, cites_any, passage_texts, restates_cited
from sec_agent.eval.agent.grounding import restates
from sec_agent.eval.agent.scenarios import result_values
from sec_agent.faithfulness.models import FaithfulnessReport, SentenceCheck

ChangeKind = Literal["added", "removed", "changed"]
KINDS: dict[ChangeKind, re.Pattern[str]] = {
    "added": re.compile(r"\b(?:add(?:s|ed|ing|itions?|itional)?|new(?:ly)?|introduc\w*)\b", re.I),
    "removed": re.compile(
        r"\b(?:remov\w*|delet\w*|dropp\w*|drops?|eliminat\w*|omit\w*|no longer)\b", re.I
    ),
    "changed": re.compile(
        r"\b(?:chang\w*|revis\w*|updat\w*|modif\w*|expand\w*|amend\w*|reword\w*)\b", re.I
    ),
}
SAME = re.compile(
    r"\bunchanged\b|\b(?:not|n't|never)\s+(?:been\s+)?(?:chang|add|remov|revis|updat|modif)\w*"
    r"|\bno (?:new|changes?|additions?)\b|\bremain(?:s|ed)?\s+(?:the same|unchanged)\b"
    r"|\bsame as\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Change:
    kind: str
    texts: tuple[str, ...]
    """The paragraph as the later filing has it and, if any, as the earlier one had it."""


def claimed_kinds(text: str) -> set[ChangeKind]:
    """The kinds of change a sentence claims; none when it says a risk stayed the same."""
    if SAME.search(text) is not None:
        return set()
    return {kind for kind, pattern in KINDS.items() if pattern.search(text) is not None}


def risk_diff_failure(
    diffs: Sequence[Evidence],
    evidence: Sequence[Evidence],
    stated: Sequence[SentenceCheck],
    report: FaithfulnessReport,
    *,
    offered: bool,
) -> Literal["outcome"] | None:
    """`diffs`: the compared diffs the check matched (the system's or the oracle's);
    `stated`: the answer's sentences that are not non-answers."""
    filings = [f for e in diffs for f in _compared(e)]
    accessions = {a for pair in filings for a in pair}
    changes = [c for e in diffs for c in _changes(e)]
    passages = {k: t for e in evidence for k, t in passage_texts(e).items()}

    def states(s: SentenceCheck) -> bool:
        if not cites_any(cited(s), accessions):
            return False
        if not offered and not restates_cited(s, passages):
            return False
        if not changes:
            return SAME.search(s.text) is not None
        kinds = claimed_kinds(s.text)
        return any(c.kind in kinds and restates(s.text, c.texts) for c in changes)

    if not any(states(s) for s in stated):
        return "outcome"
    if offered:
        return None
    keys = {k for s in report.sentences for k in cited(s)}
    both = any(all(cites_any(keys, {a}) for a in pair) for pair in filings)
    return None if both else "outcome"


def _changes(evidence: Evidence) -> list[Change]:
    found: list[Change] = []
    for rows in result_values(evidence.result, "changes"):
        if not isinstance(rows, list):
            continue
        for row in cast(list[Any], rows):
            if not isinstance(row, dict):
                continue
            change = cast(dict[str, Any], row)
            texts = tuple(
                t for t in (change.get("text"), change.get("previous_text")) if isinstance(t, str)
            )
            found.append(Change(kind=str(change.get("kind")), texts=texts))
    return found


def _compared(evidence: Evidence) -> list[tuple[str, str]]:
    """The (current, previous) accessions a compared diff names."""
    current = result_values(evidence.result, "current.accession")
    previous = result_values(evidence.result, "previous.accession")
    return [(c, p) for c in current for p in previous if isinstance(c, str) and isinstance(p, str)]
