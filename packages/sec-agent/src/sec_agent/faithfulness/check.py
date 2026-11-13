"""check_answer: trace every figure, date and citation of an answer, then decide what to show.

A sentence passes when each of its figures and dates traced and each citation key names
a passage or filing of the turn. A sentence with none of these is not checked and never
dropped. When every checked sentence passes, the answer is shown as written; otherwise
the failed sentences are dropped and a note says so, unless the config blocks, too large
a share failed, or nothing would be left: then the answer is withheld.
"""

import datetime as dt
import re
from collections.abc import Sequence

from sec_agent.agent.answer import Evidence
from sec_agent.faithfulness.config import FaithfulnessConfig
from sec_agent.faithfulness.models import (
    CitationCheck,
    FaithfulnessReport,
    SentenceCheck,
    Verdict,
)
from sec_agent.faithfulness.notices import BLOCKED_TEXT, TRIMMED_NOTE
from sec_agent.faithfulness.scan import scan
from sec_agent.faithfulness.sentences import split_sentences
from sec_agent.faithfulness.sources import Sources, collect_sources
from sec_agent.faithfulness.trace import (
    SentenceContext,
    citation_known,
    trace_date,
    trace_number,
)

_DEFAULT = FaithfulnessConfig()
_BLANK_LINES = re.compile(r"\n{3,}")
_BLOCKED: tuple[Verdict, str] = ("blocked", BLOCKED_TEXT)


def check_answer(
    text: str,
    evidence: Sequence[Evidence],
    *,
    asked_on: dt.date | None,
    config: FaithfulnessConfig = _DEFAULT,
) -> FaithfulnessReport:
    """`asked_on` is the user's date, which an answer may state (E6)."""
    sources = collect_sources(evidence)
    checked = [_check(text, s.start, s.end, sources, asked_on) for s in split_sentences(text)]
    verdict = _decide(checked, config)
    shown = text
    if verdict == "trimmed":
        remaining = _rebuild(checked)
        verdict, shown = ("trimmed", f"{remaining}\n\n{TRIMMED_NOTE}") if remaining else _BLOCKED
    elif verdict == "blocked":
        shown = BLOCKED_TEXT
    sentences = tuple(
        s.model_copy(update={"kept": verdict != "blocked" and s.passed}) for s in checked
    )
    mentions = [m for s in sentences for m in s.mentions]
    return FaithfulnessReport(
        verdict=verdict,
        text=shown,
        sentences=sentences,
        mentions=len(mentions),
        traced=sum(m.status == "traced" for m in mentions),
        faithful=all(s.passed for s in sentences),
    )


def _check(
    text: str, start: int, end: int, sources: Sources, asked_on: dt.date | None
) -> SentenceCheck:
    piece = text[start:end]
    found = scan(piece, offset=start)
    ctx = SentenceContext(
        years=found.years,
        dates=frozenset(d.date for d in found.dates if d.date is not None),
        citations=frozenset(c.key for c in found.citations),
    )
    mentions = sorted(
        [trace_number(n, ctx, sources) for n in found.numbers]
        + [trace_date(d, sources, asked_on) for d in found.dates],
        key=lambda m: m.mention.start,
    )
    citations = tuple(
        CitationCheck(
            key=c.key,
            start=c.start,
            end=c.end,
            status="valid"
            if citation_known(c.key, sources.citation_keys, sources.accessions)
            else "unknown",
        )
        for c in found.citations
    )
    passed = all(m.status == "traced" for m in mentions) and all(
        c.status == "valid" for c in citations
    )
    return SentenceCheck(
        start=start,
        end=end,
        text=piece,
        mentions=tuple(mentions),
        citations=citations,
        passed=passed,
        kept=passed,
    )


def _decide(sentences: list[SentenceCheck], config: FaithfulnessConfig) -> Verdict:
    checked = [s for s in sentences if s.mentions or s.citations]
    failed = sum(not s.passed for s in checked)
    if not failed:
        return "pass"
    if config.on_failure == "block" or failed / len(checked) > config.max_dropped_share:
        return "blocked"
    return "trimmed"


def _rebuild(sentences: list[SentenceCheck]) -> str:
    """The passed sentences in order, each line break of a dropped one kept once."""
    out = ""
    for s in sentences:
        if s.passed:
            out += s.text
            continue
        breaks = s.text[len(s.text.rstrip()) :].count("\n")
        if breaks and out:
            out = out.rstrip(" \t")
            have = len(out) - len(out.rstrip("\n"))
            out += "\n" * max(0, breaks - have)
    return _BLANK_LINES.sub("\n\n", out).strip()
