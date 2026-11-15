"""scan: the figures, full dates, named years and citation keys of one sentence.

A figure keeps the number as shown and what rounding can explain: `tolerance` is half a
unit of its last digit at its scale ("$391.0 billion" is 391.0e9 +/- 0.05e9). Its unit is
what the text says (E5): "$", "USD" or "dollars"; "per share"; "%"; "x" or "times";
"shares"; an ordinal is a rank; anything else is `none`. A sign counts only when written
("-2.5%", "(2.5)%"). Years, forms (10-K), items (Item 1A), quarters (Q3), durations
("12 months"), index names (S&P 100), links and filing ids hold digits but are not
figures; years and dates name the sentence's periods instead (E1).
"""

import datetime as dt
import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sec_agent.faithfulness import patterns as p

MentionUnit = Literal["usd", "per_share", "percent", "times", "shares", "rank", "none"]
_FROZEN = ConfigDict(frozen=True, extra="forbid")


class NumberMention(BaseModel):
    model_config = _FROZEN

    kind: Literal["number"] = "number"
    text: str
    start: int
    end: int
    value: Decimal
    """At its scale: "$391.0 billion" is 391000000000.0."""
    tolerance: Decimal
    scale: int
    """Power of ten of the scale word: 9 for billion, 0 for none."""
    unit: MentionUnit
    signed: bool


class DateMention(BaseModel):
    model_config = _FROZEN

    kind: Literal["date"] = "date"
    text: str
    start: int
    end: int
    date: dt.date | None
    """None when no such day exists (February 30)."""


class CitationMention(BaseModel):
    model_config = _FROZEN

    key: str
    start: int
    end: int


class Scan(BaseModel):
    model_config = _FROZEN

    numbers: tuple[NumberMention, ...]
    dates: tuple[DateMention, ...]
    citations: tuple[CitationMention, ...]
    years: frozenset[int]
    """Every year the sentence names: fiscal years, bare years, the years of its dates."""


def scan(text: str, *, offset: int = 0) -> Scan:
    masked = list(text)
    citations = _citations(text, masked, offset)
    years: set[int] = set()
    dates = _dates(text, masked, offset, years)
    for match in p.FISCAL_YEAR.finditer(_joined(masked)):
        raw = match["year"] or match["long"]
        years.add(int(raw) + 2000 if len(raw) == 2 else int(raw))
        _mask(masked, match)
    for pattern in p.NOT_FIGURES:
        for match in pattern.finditer(_joined(masked)):
            _mask(masked, match)
    for match in p.YEAR.finditer(_joined(masked)):
        years.add(int(match["year"]))
        _mask(masked, match)
    numbers = _numbers(text, _joined(masked), offset)
    return Scan(numbers=numbers, dates=dates, citations=citations, years=frozenset(years))


def _joined(masked: list[str]) -> str:
    return "".join(masked)


def _mask(masked: list[str], match: re.Match[str]) -> None:
    for i in range(match.start(), match.end()):
        masked[i] = " "


def _citations(text: str, masked: list[str], offset: int) -> tuple[CitationMention, ...]:
    found: list[CitationMention] = []
    for bracket in p.BRACKET.finditer(text):
        keys = list(p.CITATION_KEY.finditer(bracket[1]))
        if not keys:
            continue
        base = bracket.start(1)
        found.extend(
            CitationMention(key=k[0], start=offset + base + k.start(), end=offset + base + k.end())
            for k in keys
        )
        _mask(masked, bracket)
    return tuple(found)


def _dates(text: str, masked: list[str], offset: int, years: set[int]) -> tuple[DateMention, ...]:
    found: list[DateMention] = []
    for pattern in (p.MONTH_DAY_YEAR, p.ISO_DATE, p.US_DATE):
        for match in pattern.finditer(_joined(masked)):
            month = match["month"]
            number = p.MONTH_NUMBERS[month[:3].lower()] if month[0].isalpha() else int(month)
            year = int(match["year"])
            years.add(year)
            found.append(
                DateMention(
                    text=text[match.start() : match.end()],
                    start=offset + match.start(),
                    end=offset + match.end(),
                    date=_date(year, number, int(match["day"])),
                )
            )
            _mask(masked, match)
    for match in p.MONTH_YEAR.finditer(_joined(masked)):
        years.add(int(match["year"]))
        _mask(masked, match)
    return tuple(sorted(found, key=lambda d: d.start))


def _date(year: int, month: int, day: int) -> dt.date | None:
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def _numbers(text: str, masked: str, offset: int) -> tuple[NumberMention, ...]:
    found: list[NumberMention] = []
    for match in p.NUMBER.finditer(masked):
        start, end = match.start(), match.end()
        rest = masked[end:]
        unit = _unit(match, rest)
        if unit is None:
            continue  # digits run into a word ("5G", "H100"): a name, not a figure
        signed_by_parens = bool(match["open"] and match["close"])
        if match["open"] and not signed_by_parens:
            start += 1
        if unit in ("percent", "times"):
            suffix = (p.PERCENT_AFTER if unit == "percent" else p.TIMES_AFTER).match(rest)
            end += 0 if suffix is None else suffix.end()
        digits = match["digits"].replace(",", "")
        places = len(digits.partition(".")[2])
        scale = p.SCALES[match["scale"].lower()] if match["scale"] else 0
        signed = signed_by_parens or bool(match["minus"])
        value = Decimal(digits).scaleb(scale)
        found.append(
            NumberMention(
                text=text[start:end],
                start=offset + start,
                end=offset + end,
                value=-value if signed else value,
                tolerance=Decimal(0) if unit == "rank" else Decimal(5).scaleb(scale - places - 1),
                scale=scale,
                unit=unit,
                signed=signed,
            )
        )
    return tuple(found)


def _unit(match: re.Match[str], rest: str) -> MentionUnit | None:
    if match["ordinal"]:
        return "rank"
    if p.TIMES_AFTER.match(rest):
        return "times"
    if rest[:1].isalpha() or rest[:1].isdigit():
        return None
    if p.PERCENT_AFTER.match(rest):
        return "percent"
    if p.PER_SHARE_AFTER.match(rest):
        return "per_share"
    if match["currency"] or p.DOLLARS_AFTER.match(rest):
        return "usd"
    if p.SHARES_AFTER.match(rest):
        return "shares"
    return "none"
