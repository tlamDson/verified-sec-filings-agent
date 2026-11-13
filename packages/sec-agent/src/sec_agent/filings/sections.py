"""Text blocks to the sections the index keeps.

10-K (and 10-K/A): Item 1 Business, Item 1A Risk Factors, Item 7 MD&A, Item 7A Market Risk.
10-Q (and 10-Q/A): Part I Item 2 MD&A, Part II Item 1A Risk Factors.

A heading is a short block that starts with "Item <n>" (optionally after "Part I,") and then
a separator, a capitalised title, or nothing (the title is then the next block). A block like
"Item 7 of this report..." or "See Item 7." is a reference, not a heading. A section runs
from its heading to the next heading of any item, a "PART" line, or "SIGNATURES".

Item numbers repeat between 10-Q parts, so a section is matched by item number *and* title,
and the title must be the whole rest of the heading (a page number and punctuation aside):
"Item 1A: Risk Factors in our 2023 Form 10-K." is a cross-reference, not a section start.
"(continued)" headings repeated at page tops are neither starts nor ends. Every item heading
appears at least twice (table of contents, then body); the candidate with the longest body
wins, which skips the table of contents.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from sec_agent.filings.models import Section, SectionKey
from sec_agent.filings.tokens import count_tokens

MAX_HEADING_CHARS = 200
# Shorter bodies are cross-reference stubs ("See page 12."), not text worth indexing.
MIN_SECTION_TOKENS = 8

_DASHES = "\u2013\u2014-"
_HEADING = re.compile(
    rf"(?:part\s+(?:iv|i{{1,3}})\s*[,.:{_DASHES}]?\s*)?"
    r"items?\s+(?P<item>\d{1,2}[a-c]?)"
    rf"(?P<sep>\s*[.:{_DASHES}])?\s*"
    r"(?P<rest>.*)",
    re.IGNORECASE,
)
# "Items 1 and 2. Business and Properties": drop the second item number before the title.
_ALSO_ITEM = re.compile(rf"(?:and|&|,)\s*\d{{1,2}}[a-c]?\s*[.:{_DASHES}]?\s*", re.IGNORECASE)
_OTHER_BOUNDARY = re.compile(r"part\s+(?:iv|i{1,3})\b.*|signatures?|exhibit\s+index", re.IGNORECASE)
_CONTINUED = re.compile(r"\bcontinued\b", re.IGNORECASE)
# What may follow a title: punctuation and a table-of-contents page number.
_TITLE_TAIL = re.compile(r"[\s.:;,]*(?:(?:page\s+)?\d{1,3})?[\s.]*", re.IGNORECASE)

_MDNA = (
    r"management.{0,2}s\s+discussion\s+and\s+analysis"
    r"(?:\s+of\s+(?:the\s+)?(?:financial\s+condition|results\s+of\s+operations)"
    r"(?:,?\s+and\s+(?:financial\s+condition|results\s+of\s+operations))?)?"
)
_MARKET_RISK = (
    r"quantitative\s+and\s+qualitative\s+disclosures?\s+(?:about|of|on|regarding)\s+market\s+risks?"
)


@dataclass(frozen=True)
class SectionSpec:
    key: SectionKey
    item: str  # item number as written after "Item", upper case
    label: str
    title: re.Pattern[str]


def _spec(key: SectionKey, item: str, label: str, title: str) -> SectionSpec:
    return SectionSpec(key, item, label, re.compile(title, re.IGNORECASE))


SECTION_SPECS: dict[str, tuple[SectionSpec, ...]] = {
    "10-K": (
        _spec("business", "1", "Item 1", r"business(?:\s+and\s+properties)?"),
        _spec("risk_factors", "1A", "Item 1A", r"risk\s+factors"),
        _spec("mdna", "7", "Item 7", _MDNA),
        _spec("market_risk", "7A", "Item 7A", _MARKET_RISK),
    ),
    "10-Q": (
        _spec("mdna", "2", "Part I, Item 2", _MDNA),
        _spec("risk_factors", "1A", "Part II, Item 1A", r"risk\s+factors"),
    ),
}


@dataclass(frozen=True)
class _Heading:
    index: int
    item: str
    rest: str


def specs_for(form: str) -> tuple[SectionSpec, ...]:
    """Section specs for a form; an amendment ("10-K/A") uses its base form's specs."""
    specs = SECTION_SPECS.get(form.removesuffix("/A"))
    if specs is None:
        raise ValueError(f"no text sections are defined for form {form!r}")
    return specs


def find_sections(blocks: Sequence[str], form: str) -> list[Section]:
    specs = specs_for(form)
    headings = [h for i, block in enumerate(blocks) if (h := _parse_heading(i, block))]
    boundaries = sorted(
        {h.index for h in headings}
        | {i for i, b in enumerate(blocks) if len(b) <= 100 and _OTHER_BOUNDARY.fullmatch(b)}
    )
    sections: list[Section] = []
    for spec in specs:
        best: tuple[int, Section] | None = None
        for heading in headings:
            if heading.item != spec.item:
                continue
            section = _section_at(spec, heading, blocks, boundaries)
            if section is None:
                continue
            size = len(section.text)
            if best is None or size > best[0]:
                best = (size, section)
        if best is not None and best[1].token_count >= MIN_SECTION_TOKENS:
            sections.append(best[1])
    return sections


def _parse_heading(index: int, block: str) -> _Heading | None:
    if len(block) > MAX_HEADING_CHARS:
        return None
    match = _HEADING.fullmatch(block)
    if match is None:
        return None
    rest = match["rest"]
    if _CONTINUED.search(rest):
        return None  # "Item 7. MD&A (continued)" repeats a heading at a page top
    if also := _ALSO_ITEM.match(rest):
        rest = rest[also.end() :]
    elif match["sep"] is None and rest and not rest[0].isupper():
        return None  # "Item 7 of this report ..." is a reference inside body text
    return _Heading(index, match["item"].upper(), rest)


def _section_at(
    spec: SectionSpec, heading: _Heading, blocks: Sequence[str], boundaries: Sequence[int]
) -> Section | None:
    title, body_start = heading.rest, heading.index + 1
    heading_text = blocks[heading.index]
    if not title and body_start < len(blocks):
        title = blocks[body_start]  # "Item 1A." in one block, "Risk Factors" in the next
        heading_text = f"{heading_text} {title}"
        body_start += 1
    if not _is_title(spec, title):
        return None
    end = next((b for b in boundaries if b >= body_start), len(blocks))
    text = "\n".join(blocks[body_start:end])
    return Section(
        key=spec.key,
        item=spec.label,
        heading=heading_text,
        text=text,
        token_count=count_tokens(text),
    )


def _is_title(spec: SectionSpec, text: str) -> bool:
    match = spec.title.match(text)
    return match is not None and _TITLE_TAIL.fullmatch(text, match.end()) is not None
