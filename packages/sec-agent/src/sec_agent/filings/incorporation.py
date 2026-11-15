"""10-K items incorporated by reference to Exhibit 13, and filling them from its text.

Some 10-Ks (banks, telecoms) answer Items 1A, 7 and 7A with a one-sentence pointer:
"Information in response to this Item 7 can be found in the 2024 Annual Report to
Shareholders under 'Financial Review.' That information is incorporated into this item by
reference." Indexing only that sentence leaves the company with boilerplate chunks. An item
is *incorporated* when it is such a short pointer, or missing from a 10-K. Only incorporated
items are filled from the exhibit; an item the 10-K writes itself is never replaced.
"""

import re
from collections.abc import Sequence

from sec_agent.filings.models import Section, SectionKey

# The pointers seen run 30 to 80 tokens; a real item is hundreds or thousands.
STUB_MAX_TOKENS = 150
ANNUAL_KEYS: tuple[SectionKey, ...] = ("risk_factors", "mdna", "market_risk")
_ORDER: tuple[SectionKey, ...] = ("business", "risk_factors", "mdna", "market_risk")
_POINTER = re.compile(
    r"\bincorporat\w*\b.{0,80}\bby\s+reference\b"
    r"|\bannual\s+report\s+to\s+(?:share|stock)holders\b"
    r"|\bexhibit\s+13\b",
    re.IGNORECASE | re.DOTALL,
)


def incorporated_keys(sections: Sequence[Section], form: str) -> set[SectionKey]:
    """Annual items of a 10-K (or 10-K/A) that point elsewhere or are missing."""
    if form.removesuffix("/A") != "10-K":
        return set()
    found = {s.key: s for s in sections}
    return {key for key in ANNUAL_KEYS if key not in found or _is_pointer(found[key])}


def merge_sections(
    primary: Sequence[Section], exhibit: Sequence[Section], form: str
) -> list[Section]:
    """The primary sections, with each incorporated item taken from the exhibit if it has it."""
    wanted = incorporated_keys(primary, form)
    chosen = {s.key: s for s in primary}
    for section in exhibit:
        if section.key in wanted:
            chosen[section.key] = section
    return [chosen[key] for key in _ORDER if key in chosen]


def _is_pointer(section: Section) -> bool:
    return section.token_count <= STUB_MAX_TOKENS and _POINTER.search(section.text) is not None
