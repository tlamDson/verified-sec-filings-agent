"""Exhibit 13 (annual report to shareholders) text blocks to the sections the index keeps.

An annual report has no "Item" headings. Its parts are found by title: MD&A is
"Management's Discussion and Analysis ..." or "Financial Review" (how some banks title
it), risk factors are "Risk Factors", market risk is "Quantitative and Qualitative
Disclosures About Market Risk". A part ends at the next title of another part, or at a
title that starts what follows MD&A: controls, the auditor's and management's reports,
the financial statements and their notes, a glossary.

A heading is a short block that is exactly a title (a page number and punctuation aside),
optionally followed by "(continued)". Reports repeat a part's title at page tops, so
consecutive headings of the same part join into one run and are left out of its text.
The table of contents repeats every title too; the longest run of a part wins, which
skips it. Business is never taken from an annual report: a 10-K always writes Item 1.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sec_agent.filings.models import Section, SectionKey
from sec_agent.filings.sections import (
    MARKET_RISK_TITLE,
    MDNA_TITLE,
    MIN_SECTION_TOKENS,
    TITLE_TAIL,
)
from sec_agent.filings.tokens import count_tokens

EXHIBIT_ITEM = "Exhibit 13"
MAX_HEADING_CHARS = 120

_KEY_ORDER: tuple[SectionKey, ...] = ("business", "risk_factors", "mdna", "market_risk")
_CONTINUED = re.compile(r"\s*[(\[]?\s*continued\s*[)\]]?\s*$", re.IGNORECASE)


def _title(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


_PART_TITLES: tuple[tuple[SectionKey, re.Pattern[str]], ...] = (
    ("mdna", _title(MDNA_TITLE)),
    ("mdna", _title(r"financial\s+review")),
    ("risk_factors", _title(r"risk\s+factors")),
    ("market_risk", _title(MARKET_RISK_TITLE)),
)
_OTHER_TITLES: tuple[re.Pattern[str], ...] = tuple(
    _title(p)
    for p in (
        r"controls\s+and\s+procedures",
        r"financial\s+statements(?:\s+and\s+supplementary\s+data)?",
        r"report\s+of\s+independent\s+registered\s+public\s+accounting\s+firm",
        r"(?:management.{0,2}s\s+)?(?:annual\s+)?report\s+on\s+internal\s+control\b.*",
        r"report\s+of\s+management\b.*",
        r"consolidated\s+(?:balance\s+sheets?|income\s+statements?|statements?\s+of\s+[a-z ,]+)",
        r"notes\s+to\s+(?:the\s+)?(?:consolidated\s+)?financial\s+statements",
        r"glossary(?:\s+of\s+[a-z ]+)?",
        r"selected\s+financial\s+data",
        r"signatures?|exhibit\s+index",
    )
)

_Part = SectionKey | Literal["other"]


@dataclass(frozen=True)
class _Run:
    key: _Part
    heading: str
    body: tuple[str, ...]


def find_annual_report_sections(blocks: Sequence[str], source_url: str) -> list[Section]:
    best: dict[SectionKey, tuple[int, Section]] = {}
    for run in _runs(blocks):
        if run.key == "other":
            continue
        text = "\n".join(run.body)
        section = Section(
            key=run.key,
            item=EXHIBIT_ITEM,
            heading=run.heading,
            text=text,
            token_count=count_tokens(text),
            source_url=source_url,
        )
        if section.token_count >= MIN_SECTION_TOKENS and (
            run.key not in best or len(text) > best[run.key][0]
        ):
            best[run.key] = (len(text), section)
    return [best[key][1] for key in _KEY_ORDER if key in best]


def _runs(blocks: Sequence[str]) -> list[_Run]:
    runs: list[_Run] = []
    key: _Part | None = None
    heading = ""
    body: list[str] = []
    for block in blocks:
        part = _heading_part(block)
        if part is None:
            if key is not None:
                body.append(block)
            continue
        if part == key and part != "other":
            continue  # the part's title repeated at a page top
        if key is not None:
            runs.append(_Run(key, heading, tuple(body)))
        key, heading, body = part, block, []
    if key is not None:
        runs.append(_Run(key, heading, tuple(body)))
    return runs


def _heading_part(block: str) -> _Part | None:
    if len(block) > MAX_HEADING_CHARS:
        return None
    text = _CONTINUED.sub("", block)
    for key, title in _PART_TITLES:
        if _is_title(title, text):
            return key
    if any(_is_title(title, text) for title in _OTHER_TITLES):
        return "other"
    return None


def _is_title(title: re.Pattern[str], text: str) -> bool:
    match = title.match(text)
    return match is not None and TITLE_TAIL.fullmatch(text, match.end()) is not None
