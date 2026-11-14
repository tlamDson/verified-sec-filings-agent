"""Whether a cited sentence restates its source, or only points at it.

"[0001-24-000001/risk_factors/3]" or "See the 10-K for details [...]" cites a passage and
states nothing. A sentence restates a source when, its citation markers removed, it shares
at least `MIN_SHARED` content words with that source's text. Words are compared by their
first five letters, so "depends" meets "depend" and "casing" meets "casings"; generic
words of any filing answer ("risk", "factor", "company", "filing"...) do not count.
The passing text answers of the committed A1 transcripts share 15 to 32 such words with
the passage they cite; citations alone share none. Code decides it, never a model.
"""

import re
from collections.abc import Iterable

MIN_SHARED = 5
_STEM = 5
_CITATION = re.compile(r"\[[^\]]*\]")
_WORD = re.compile(r"[a-z]{4,}")
_GENERIC = frozenset(
    {
        "about", "also", "annual", "based", "been", "being", "company", "could", "describe",
        "described", "describes", "details", "factor", "factors", "filing", "filings", "following",
        "form", "from", "have", "including", "into", "item", "more", "other", "passage",
        "passages", "provided", "report", "reports", "risk", "risks", "said", "says", "section",
        "should", "simulated", "states", "such", "than", "that", "their", "them", "there",
        "these", "they", "this", "those", "through", "under", "were", "what", "when", "which",
        "will", "with", "would", "year", "years",
    }
)  # fmt: skip


def stems(text: str) -> frozenset[str]:
    words = _WORD.findall(_CITATION.sub(" ", text).lower())
    return frozenset(w[:_STEM] for w in words if w not in _GENERIC)


def restates(sentence: str, sources: Iterable[str]) -> bool:
    """Whether `sentence` shares `MIN_SHARED` content words with one of `sources`."""
    said = stems(sentence)
    return any(len(said & stems(source)) >= MIN_SHARED for source in sources)
