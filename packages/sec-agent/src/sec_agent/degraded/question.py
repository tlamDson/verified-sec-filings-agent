"""read_question: the companies, figures and fiscal years a question names, by fixed rules.

A company is found by its ticker written in capitals (or after "$"), a former ticker or
name (E8), its full name in any case, or the capitalised first word of a longer name
("Meta"). Ordinary lower-case words are never read as tickers. Years are the company's
fiscal years as written (E1); a span ("last 3 years") is counted back from the latest
reported year by the lookup, not from the calendar.
"""

import re
from dataclasses import dataclass

from sec_agent.degraded.lexicon import Metric, find_metrics, words
from sec_agent.tools.companies import CompanyDirectory, CompanyRef
from sec_agent.xbrl.calendar import FiscalPeriod

MAX_COMPANIES = 4
MAX_YEARS = 5
MAX_NAME_WORDS = 4
MIN_FIRST_WORD_CHARS = 3
MAX_SHOUTED_TOKENS = 4
_MIN_YEAR, _MAX_YEAR = 1990, 2100

_TOKEN = re.compile(r"\$?[A-Za-z0-9]+(?:[.&'\u2019-][A-Za-z0-9]+)*")
_POSSESSIVE = re.compile(r"['\u2019]s$", re.IGNORECASE)
_COMMON_FIRST_WORDS = frozenset(
    {
        "advanced",
        "american",
        "applied",
        "bank",
        "booking",
        "capital",
        "charles",
        "duke",
        "general",
        "home",
        "intuitive",
        "palo",
        "philip",
        "southern",
        "texas",
        "union",
        "united",
        "walt",
    }
)
"""First words of company names that also start ordinary sentences ("Capital
expenditures..."); such a company is found by its full name or ticker only."""

_YEAR = r"(?:19|20)\d{2}"
_YEAR_RANGE = re.compile(rf"\b({_YEAR})\s*(?:-|\u2013|to|through)\s*({_YEAR})\b")
_ONE_YEAR = re.compile(rf"\b(?:fy\s?)?({_YEAR})\b")
_COUNTS = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_SPAN = re.compile(
    rf"\b(?:last|past|previous|trailing)\s+(\d{{1,3}}|{'|'.join(_COUNTS)})\s+(?:fiscal\s+)?years\b"
)
_QUARTER = re.compile(r"\bq([1-4])\b|\b(first|second|third|fourth)\s+quarter\b")
_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4}
_GROWTH = re.compile(r"\b(?:grow\w*|grew|yoy|year over year|year on year)\b")
_PEERS = re.compile(r"\b(?:peers?|sector|competitors?|rivals?|industry)\b")
_RISK = re.compile(r"\brisks?\b")
_CHANGE = re.compile(r"\b(?:new|add|added|removed?|changed?|changes|differ\w*|dropped)\b")


@dataclass(frozen=True)
class QuestionParts:
    companies: tuple[CompanyRef, ...]
    metrics: tuple[Metric, ...]
    years: tuple[int, ...]
    """Fiscal years written in the question, ascending; empty when none is."""
    span: int | None
    """"The last N years": N fiscal years ending at the latest reported one."""
    fiscal_period: FiscalPeriod
    growth: bool
    peers: bool
    risk_changes: bool


def read_question(question: str, directory: CompanyDirectory) -> QuestionParts:
    text = words(question)
    return QuestionParts(
        companies=find_companies(question, directory),
        metrics=find_metrics(question),
        years=_years(question.casefold()),
        span=_span(text),
        fiscal_period=_fiscal_period(text),
        growth=_GROWTH.search(text) is not None,
        peers=_PEERS.search(text) is not None,
        risk_changes=_RISK.search(text) is not None and _CHANGE.search(text) is not None,
    )


def find_companies(question: str, directory: CompanyDirectory) -> tuple[CompanyRef, ...]:
    """The companies named, in the order named, each once, at most `MAX_COMPANIES`."""
    tokens = [m.group() for m in _TOKEN.finditer(question)]
    shouted = len(tokens) > MAX_SHOUTED_TOKENS and not any(c.islower() for c in question)
    found: dict[int, tuple[int, CompanyRef]] = {}

    def note(position: int, company: CompanyRef | None) -> None:
        if company is not None and (company.cik not in found or position < found[company.cik][0]):
            found[company.cik] = (position, company)

    for position, token in enumerate(tokens):
        note(position, _by_symbol(token, directory, shouted=shouted))
        note(position, _by_first_word(token, directory))
        for size in range(1, MAX_NAME_WORDS + 1):
            note(position, _by_name(tokens[position : position + size], directory))
    ordered = sorted(found.values(), key=lambda item: item[0])
    return tuple(company for _, company in ordered[:MAX_COMPANIES])


def _by_symbol(token: str, directory: CompanyDirectory, *, shouted: bool) -> CompanyRef | None:
    if token.startswith("$"):
        return directory.by_ticker(token[1:])
    bare = _POSSESSIVE.sub("", token)
    written_as_ticker = len(bare) >= 2 and bare == bare.upper() and any(c.isalpha() for c in bare)
    if written_as_ticker and not shouted and (company := directory.by_ticker(bare)) is not None:
        return company
    return directory.by_alias(bare)


def _by_first_word(token: str, directory: CompanyDirectory) -> CompanyRef | None:
    word = _POSSESSIVE.sub("", token)
    if len(word) < MIN_FIRST_WORD_CHARS or not word[0].isupper() or not word.isalpha():
        return None
    if word.casefold() in _COMMON_FIRST_WORDS:
        return None
    return directory.name_starting(word)


def _by_name(tokens: list[str], directory: CompanyDirectory) -> CompanyRef | None:
    """A run of tokens that is one company's whole name, with or without a possessive."""
    if not tokens or any(t.startswith("$") for t in tokens):
        return None
    if len(tokens) > 1 and any(len(t) == 1 for t in tokens):
        return None  # "at t" is two stray words, not AT&T
    phrase = " ".join(tokens)
    return directory.by_name(phrase) or directory.by_name(_POSSESSIVE.sub("", phrase))


def _years(text: str) -> tuple[int, ...]:
    years: set[int] = set()
    for match in _YEAR_RANGE.finditer(text):
        first, last = sorted((int(match[1]), int(match[2])))
        years.update(range(max(first, last - MAX_YEARS + 1), last + 1))
    years.update(int(match[1]) for match in _ONE_YEAR.finditer(text))
    kept = sorted(y for y in years if _MIN_YEAR <= y <= _MAX_YEAR)
    return tuple(kept[-MAX_YEARS:])


def _span(text: str) -> int | None:
    match = _SPAN.search(text)
    if match is None:
        return None
    count = _COUNTS.get(match[1]) or int(match[1])
    return min(count, MAX_YEARS) if count >= 2 else None


def _fiscal_period(text: str) -> FiscalPeriod:
    match = _QUARTER.search(text)
    if match is None:
        return "FY"
    quarter = int(match[1]) if match[1] else _ORDINALS[match[2]]
    periods: tuple[FiscalPeriod, ...] = ("Q1", "Q2", "Q3", "Q4")
    return periods[quarter - 1]
