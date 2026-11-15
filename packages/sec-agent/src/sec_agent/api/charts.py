"""charts_of: the chart series a turn's cards can be drawn as.

A trend is one metric of one fiscal period type over two or more fiscal years, one series
per company; the x axis is each company's own fiscal year and every point keeps its own
period end (E3). A peer comparison is one bar per company that has a value. A point is
always the value of one card: a value that was not reported is a gap, never a guess.
"""

import datetime as dt
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import NamedTuple

from sec_agent.api.cards import (
    Card,
    Chart,
    ChartPoint,
    ChartSeries,
    FactCard,
    PeersCard,
    RatioCard,
)

MIN_POINTS = 2


class _Axis(NamedTuple):
    """What may share one chart: the same metric, unit and kind of fiscal period."""

    metric: str
    unit: str
    quarter: str | None


class _Value(NamedTuple):
    ticker: str
    fiscal_year: int
    value: Decimal
    period_end: dt.date | None


def charts_of(cards: Sequence[Card]) -> tuple[Chart, ...]:
    """Trend charts in the order their metric first appears, then peer charts."""
    return (*_trends(cards), *(c for c in map(_peers, cards) if c is not None))


def period_label(fiscal_year: int, fiscal_period: str) -> str:
    return f"FY{fiscal_year}" if fiscal_period == "FY" else f"{fiscal_period} FY{fiscal_year}"


def _trends(cards: Sequence[Card]) -> list[Chart]:
    titles: dict[_Axis, str] = {}
    values: dict[_Axis, dict[tuple[str, int], _Value]] = {}
    for card in cards:
        if not isinstance(card, FactCard | RatioCard) or card.value is None:
            continue
        title = card.label if isinstance(card, FactCard) else _ratio_title(card)
        metric = card.concept if isinstance(card, FactCard) else f"{card.ratio}:{title}"
        axis = _Axis(metric, card.unit, None if card.fiscal_period == "FY" else card.fiscal_period)
        titles.setdefault(axis, title)
        point = _Value(card.company.ticker, card.fiscal_year, card.value, card.period_end)
        values.setdefault(axis, {}).setdefault((point.ticker, point.fiscal_year), point)
    charts: list[Chart] = []
    for axis, found in values.items():
        series = _series(found.values(), axis.quarter or "FY")
        if any(len(s.points) >= MIN_POINTS for s in series):
            charts.append(Chart(kind="trend", title=titles[axis], unit=axis.unit, series=series))
    return charts


def _ratio_title(card: RatioCard) -> str:
    """A growth label names the year compared with ("Revenue, change from fiscal 2023"),
    which differs per point; its chart is titled by the concept alone."""
    concept, changed, _ = card.label.partition(", change from")
    return f"{concept}, year-over-year change" if changed else card.label


def _series(values: Iterable[_Value], fiscal_period: str) -> tuple[ChartSeries, ...]:
    by_company: dict[str, list[_Value]] = {}
    for value in values:
        by_company.setdefault(value.ticker, []).append(value)
    return tuple(
        ChartSeries(
            name=ticker,
            points=tuple(
                ChartPoint(
                    x=period_label(v.fiscal_year, fiscal_period),
                    value=v.value,
                    period_end=v.period_end,
                )
                for v in sorted(points, key=lambda v: v.fiscal_year)
            ),
        )
        for ticker, points in by_company.items()
    )


def _peers(card: Card) -> Chart | None:
    if not isinstance(card, PeersCard):
        return None
    points = tuple(
        ChartPoint(x=row.company.ticker, value=row.value, period_end=row.period_end)
        for row in sorted(card.rows, key=lambda r: (r.rank is None, r.rank or 0))
        if row.value is not None
    )
    if len(points) < MIN_POINTS:
        return None
    title = f"{card.label}, {period_label(card.fiscal_year, card.fiscal_period)}"
    return Chart(
        kind="peers",
        title=title,
        unit=card.unit,
        series=(ChartSeries(name=card.label, points=points),),
    )
