"""collect_sources: everything of a turn's evidence an answer may state, with where it is.

Each tool result is read back into its own result model, so only fields the tools define
are sources: values with their unit and period, ranks, counts, dates, filing ids, and
filing text (passages, risk-factor paragraphs) with the citation keys that cite it. A
refusal, or a result that does not read back, is no source.
"""

import datetime as dt
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, get_args

from pydantic import BaseModel, ValidationError

from sec_agent.agent.answer import Evidence
from sec_agent.faithfulness import patterns
from sec_agent.faithfulness.models import SourceRef
from sec_agent.faithfulness.scan import NumberMention, scan
from sec_agent.tools.fact_value import FactValue
from sec_agent.tools.get_fact import GetFactResult
from sec_agent.tools.peers import PeerComparison
from sec_agent.tools.ratios import RatioResult
from sec_agent.tools.risk_factors import RiskDiffResult
from sec_agent.tools.search_filings import SearchResult

SourceUnit = Literal["USD", "USD/shares", "shares", "percent", "times", "count", "rank"]
_UNITS: frozenset[str] = frozenset(get_args(SourceUnit))
_RESULTS: dict[str, type[BaseModel]] = {
    "get_fact": GetFactResult,
    "compute_ratio": RatioResult,
    "compare_peers": PeerComparison,
    "search_filings": SearchResult,
    "diff_risk_factors": RiskDiffResult,
}


@dataclass(frozen=True)
class Figure:
    value: Decimal
    unit: SourceUnit
    fiscal_year: int | None
    period_start: dt.date | None
    period_end: dt.date | None
    ref: SourceRef


@dataclass(frozen=True)
class SourceText:
    """Filing text a sentence may quote numbers from when it cites one of `keys`."""

    keys: frozenset[str]
    numbers: tuple[NumberMention, ...]
    ref: SourceRef


@dataclass
class Sources:
    figures: list[Figure] = field(default_factory=list[Figure])
    texts: list[SourceText] = field(default_factory=list[SourceText])
    dates: dict[dt.date, SourceRef] = field(default_factory=dict[dt.date, SourceRef])
    citation_keys: set[str] = field(default_factory=set[str])
    """Passage citations, `accession/section/ordinal`."""
    accessions: set[str] = field(default_factory=set[str])
    """Filings named in the evidence; a bare accession cites the filing."""


def collect_sources(evidence: Sequence[Evidence]) -> Sources:
    sources = Sources()
    for item in evidence:
        model = _RESULTS.get(item.name)
        if not item.ok or model is None:
            continue
        try:
            result = model.model_validate_json(item.result)
        except ValidationError:
            continue
        _Reader(sources, item).read(result)
    return sources


class _Reader:
    def __init__(self, sources: Sources, evidence: Evidence) -> None:
        self._s = sources
        self._call_id = evidence.call_id
        self._tool = evidence.name

    def read(self, result: BaseModel) -> None:
        if isinstance(result, GetFactResult):
            if result.fact is not None:
                self._fact(result.fact, "fact")
        elif isinstance(result, RatioResult):
            self._ratio(result)
        elif isinstance(result, PeerComparison):
            self._peers(result)
        elif isinstance(result, SearchResult):
            self._search(result)
        elif isinstance(result, RiskDiffResult):
            self._risk_diff(result)

    def _ref(self, path: str, citation: str | None = None) -> SourceRef:
        return SourceRef(call_id=self._call_id, tool=self._tool, field=path, citation=citation)

    def _figure(
        self,
        value: Decimal | int | None,
        unit: str,
        path: str,
        *,
        fiscal_year: int | None = None,
        period: tuple[dt.date | None, dt.date | None] = (None, None),
    ) -> None:
        if value is None or unit not in _UNITS:
            return
        self._s.figures.append(
            Figure(
                value=Decimal(value),
                unit=unit,  # pyright: ignore[reportArgumentType]  # checked against _UNITS
                fiscal_year=fiscal_year,
                period_start=period[0],
                period_end=period[1],
                ref=self._ref(path),
            )
        )

    def _dates(self, path: str, *dates: tuple[str, dt.date | None]) -> None:
        for name, date in dates:
            if date is not None:
                self._s.dates.setdefault(date, self._ref(f"{path}.{name}" if path else name))

    def _fact(self, fact: FactValue, path: str) -> None:
        period = (fact.period_start, fact.period_end)
        year = fact.fiscal_year
        self._figure(fact.value, fact.unit, f"{path}.value", fiscal_year=year, period=period)
        if fact.original_value != fact.value:
            self._figure(
                fact.original_value,
                fact.unit,
                f"{path}.original_value",
                fiscal_year=year,
                period=period,
            )
        self._dates(
            path,
            ("period_start", fact.period_start),
            ("period_end", fact.period_end),
            ("filed", fact.filed),
            ("original_filed", fact.original_filed),
        )
        self._s.accessions.update((fact.accession, fact.original_accession))

    def _facts(self, facts: Iterable[FactValue], path: str) -> None:
        for i, fact in enumerate(facts):
            self._fact(fact, f"{path}[{i}]")

    def _ratio(self, r: RatioResult) -> None:
        period = (r.period_start, r.period_end)
        self._figure(r.value, r.unit, "value", fiscal_year=r.fiscal_year, period=period)
        self._dates("", ("period_start", r.period_start), ("period_end", r.period_end))
        self._facts(r.inputs, "inputs")

    def _peers(self, c: PeerComparison) -> None:
        self._figure(len(c.rows), "count", "rows")
        for i, row in enumerate(c.rows):
            path = f"rows[{i}]"
            period = (row.period_start, row.period_end)
            year = c.fiscal_year
            self._figure(row.value, c.unit, f"{path}.value", fiscal_year=year, period=period)
            self._figure(row.rank, "rank", f"{path}.rank")
            self._dates(path, ("period_start", row.period_start), ("period_end", row.period_end))
            self._facts(row.inputs, f"{path}.inputs")

    def _search(self, s: SearchResult) -> None:
        for i, passage in enumerate(s.passages):
            path = f"passages[{i}]"
            self._text(passage.text, {passage.citation}, f"{path}.text", passage.citation)
            self._s.citation_keys.add(passage.citation)
            self._s.accessions.add(passage.accession)
            self._dates(
                path, ("filing_date", passage.filing_date), ("report_date", passage.report_date)
            )

    def _risk_diff(self, d: RiskDiffResult) -> None:
        for name in ("added", "removed", "changed", "unchanged", "changes_total"):
            self._figure(getattr(d, name), "count", name)
        current = None if d.current is None else d.current.accession
        previous = None if d.previous is None else d.previous.accession
        for name, filing in (("current", d.current), ("previous", d.previous)):
            if filing is not None:
                self._s.accessions.add(filing.accession)
                self._dates(
                    name, ("filing_date", filing.filing_date), ("report_date", filing.report_date)
                )
        for i, change in enumerate(d.changes):
            if change.text is not None and current is not None:
                self._text(change.text, {current}, f"changes[{i}].text", current)
            if change.previous_text is not None and previous is not None:
                self._text(
                    change.previous_text, {previous}, f"changes[{i}].previous_text", previous
                )

    def _text(self, text: str, keys: set[str], path: str, citation: str) -> None:
        numbers = _at_stated_scale(text, scan(text).numbers)
        if numbers:
            self._s.texts.append(SourceText(frozenset(keys), numbers, self._ref(path, citation)))


def _at_stated_scale(text: str, numbers: tuple[NumberMention, ...]) -> tuple[NumberMention, ...]:
    """The numbers of a passage, plus each bare number at the one scale its text states.

    A table "in millions" writes 12,345 for 12,345,000,000, so that value is a source too.
    No other scale is: a passage that states none, or several, supports its bare numbers
    only as written, so an answer cannot give them a scale the filing does not.
    """
    stated = {m["scale"].lower() for m in patterns.STATED_SCALE.finditer(text)}
    if len(stated) != 1:
        return numbers
    scale = patterns.SCALES[stated.pop()]
    scaled = tuple(
        n.model_copy(
            update={
                "value": n.value.scaleb(scale),
                "tolerance": n.tolerance.scaleb(scale),
                "scale": scale,
            }
        )
        for n in numbers
        if n.scale == 0 and n.unit in ("none", "usd", "shares")
    )
    return numbers + scaled
