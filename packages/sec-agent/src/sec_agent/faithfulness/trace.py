"""Tracing one mention of a sentence to the sources of its turn.

A figure traces to a tool value when rounding that value to the digits shown gives it
(within `tolerance`), the units agree (E5), and the value's period is one the sentence
names, or the sentence names none (E1). Without a written sign the magnitude is compared,
since "fell 2.5%" states -2.5 in words. Among several matches the closest wins. A figure
traces to filing text only through a passage the sentence cites, at the value the passage
states (a bare table number also at the scale its heading states, see `sources`). A
date traces when the evidence holds it or it is the day the question was asked.
"""

import datetime as dt
from collections.abc import Collection
from dataclasses import dataclass
from decimal import Decimal

from sec_agent.faithfulness.models import MentionCheck, MentionStatus, SourceRef
from sec_agent.faithfulness.scan import DateMention, MentionUnit, NumberMention
from sec_agent.faithfulness.sources import Figure, Sources, SourceUnit

_ACCEPTS: dict[MentionUnit, frozenset[SourceUnit]] = {
    "usd": frozenset({"USD", "USD/shares"}),
    "per_share": frozenset({"USD/shares"}),
    "percent": frozenset({"percent"}),
    "times": frozenset({"times"}),
    "shares": frozenset({"shares"}),
    "rank": frozenset({"rank"}),
    "none": frozenset({"USD", "USD/shares", "shares", "percent", "times", "count"}),
}
_SAME_TEXT_UNIT: dict[MentionUnit, frozenset[MentionUnit]] = {
    "usd": frozenset({"usd", "per_share"}),
    "per_share": frozenset({"usd", "per_share"}),
}
_NEAR_MISS: tuple[MentionStatus, ...] = ("wrong_period", "uncited", "wrong_unit")


@dataclass(frozen=True)
class SentenceContext:
    years: frozenset[int]
    dates: frozenset[dt.date]
    citations: frozenset[str]


def trace_number(mention: NumberMention, ctx: SentenceContext, sources: Sources) -> MentionCheck:
    best: tuple[Decimal, SourceRef] | None = None
    misses: dict[MentionStatus, SourceRef] = {}
    for figure in sources.figures:
        gap = _gap(mention, figure.value)
        if gap is None:
            continue
        if figure.unit not in _ACCEPTS[mention.unit]:
            misses.setdefault("wrong_unit", figure.ref)
        elif not _in_period(figure, ctx):
            misses.setdefault("wrong_period", figure.ref)
        elif best is None or gap < best[0]:
            best = (gap, figure.ref)
    if best is not None:
        return MentionCheck(mention=mention, status="traced", source=best[1])
    for text in sources.texts:
        for number in text.numbers:
            if not _text_match(mention, number):
                continue
            cited = ctx.citations & text.keys
            if cited:
                ref = text.ref.model_copy(update={"citation": min(cited)})
                return MentionCheck(mention=mention, status="traced", source=ref)
            misses.setdefault("uncited", text.ref)
    for status in _NEAR_MISS:
        if status in misses:
            return MentionCheck(mention=mention, status=status, source=misses[status])
    return MentionCheck(mention=mention, status="untraced", source=None)


def trace_date(mention: DateMention, sources: Sources, asked_on: dt.date | None) -> MentionCheck:
    date = mention.date
    if date is not None and date in sources.dates:
        return MentionCheck(mention=mention, status="traced", source=sources.dates[date])
    if date is not None and date == asked_on:
        ref = SourceRef(call_id=None, tool=None, field="asked_on")
        return MentionCheck(mention=mention, status="traced", source=ref)
    return MentionCheck(mention=mention, status="untraced", source=None)


def citation_known(key: str, keys: Collection[str], accessions: Collection[str]) -> bool:
    return key in keys if "/" in key else key in accessions


def _gap(mention: NumberMention, value: Decimal) -> Decimal | None:
    """How far the shown figure is from `value`, or None when rounding cannot explain it."""
    gap = abs(mention.value - value) if mention.signed else abs(abs(mention.value) - abs(value))
    return gap if gap <= mention.tolerance else None


def _in_period(figure: Figure, ctx: SentenceContext) -> bool:
    if not ctx.years and not ctx.dates:
        return True
    if figure.fiscal_year is None and figure.period_end is None:
        return True  # a count or a rank has no period of its own
    end = figure.period_end
    return (
        figure.fiscal_year in ctx.years
        or (end is not None and (end.year in ctx.years or end in ctx.dates))
        or (figure.period_start is not None and figure.period_start in ctx.dates)
    )


def _text_match(mention: NumberMention, number: NumberMention) -> bool:
    if mention.unit != "none" and number.unit != "none":
        same = _SAME_TEXT_UNIT.get(mention.unit, frozenset({mention.unit}))
        if number.unit not in same:
            return False
    return _gap(mention, number.value) is not None
