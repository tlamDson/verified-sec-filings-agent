"""compute_ratio: a ratio of two reported facts, or a year-over-year change, done in code.

A ratio is computed only when both parts are reported for exactly the same period and the
denominator is positive; growth only when the prior value is not zero. Otherwise the result
says which part is missing (`not_reported`, E12) or why it is `undefined`. Nothing is
estimated, derived from other lines, or combined across periods.
"""

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.tools.companies import CompanyRef
from sec_agent.tools.context import FactsContext
from sec_agent.tools.errors import InvalidRequestError, UnknownMetricError
from sec_agent.tools.fact_value import FactValue
from sec_agent.tools.metrics import require_concept
from sec_agent.tools.periods import FiscalYear, PeriodRequest, pick_fact, resolve_period
from sec_agent.tools.ratio_defs import GROWTH, PLACES_TEXT, RATIOS, RatioDef, RatioUnit
from sec_agent.xbrl.calendar import FiscalPeriod
from sec_agent.xbrl.concepts import Concept
from sec_agent.xbrl.periods import PeriodKind
from sec_agent.xbrl.versions import LatestFact

PLACES = Decimal(PLACES_TEXT)


class ComputeRatioArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(min_length=1, max_length=100, description="Ticker, CIK or name.")
    ratio: str = Field(min_length=1, max_length=100, description=f"A ratio name, or {GROWTH}.")
    concept: str | None = Field(
        default=None, max_length=100, description=f"The concept whose {GROWTH} is asked."
    )
    fiscal_year: FiscalYear
    fiscal_period: FiscalPeriod = "FY"
    year_to_date: bool = False


class RatioResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["computed", "not_reported", "undefined"]
    company: CompanyRef
    ratio: str
    label: str
    formula: str
    unit: RatioUnit
    fiscal_year: int
    fiscal_period: FiscalPeriod
    period_kind: PeriodKind
    period_start: dt.date | None
    period_end: dt.date | None
    value: Decimal | None
    reason: str | None
    inputs: tuple[FactValue, ...]
    index_version: str


def require_ratio(name: str) -> RatioDef:
    found = RATIOS.get(name)
    if found is None:
        names = ", ".join([*RATIOS, GROWTH])
        raise UnknownMetricError(f"{name!r} is not a ratio these tools compute ({names})")
    return found


def compute_ratio(ctx: FactsContext, args: ComputeRatioArgs) -> RatioResult:
    company = ctx.companies.resolve(args.company)
    if args.ratio == GROWTH:
        if args.concept is None:
            raise InvalidRequestError(f"{GROWTH} needs the concept whose change is asked")
        concept = require_concept(args.concept)
        period = resolve_period(concept, args.fiscal_period, year_to_date=args.year_to_date)
        years = (args.fiscal_year - 1, args.fiscal_year)
        facts = ctx.facts.lookup(
            index_version=ctx.index_version,
            ciks=(company.cik,),
            concepts=(concept.name,),
            fiscal_years=years,
        )
        return growth_result(facts, company, concept, args.fiscal_year, period, ctx.index_version)
    definition = require_ratio(args.ratio)
    period = resolve_period(
        require_concept(definition.denominator),
        args.fiscal_period,
        year_to_date=args.year_to_date,
    )
    facts = ctx.facts.lookup(
        index_version=ctx.index_version,
        ciks=(company.cik,),
        concepts=(definition.numerator, definition.denominator),
        fiscal_years=(args.fiscal_year,),
    )
    return ratio_result(facts, company, definition, args.fiscal_year, period, ctx.index_version)


def ratio_result(
    facts: Sequence[LatestFact],
    company: CompanyRef,
    definition: RatioDef,
    fiscal_year: int,
    period: PeriodRequest,
    index_version: str,
) -> RatioResult:
    """The ratio from `facts` (pure: `compare_peers` calls it for every company)."""
    parts = [
        pick_fact(
            facts,
            cik=company.cik,
            concept=require_concept(name),
            fiscal_year=fiscal_year,
            period=period,
        )
        for name in (definition.numerator, definition.denominator)
    ]
    num, den = parts
    value: Decimal | None = None
    reason: str | None = None
    if num is None or den is None:
        missing = [
            n
            for n, p in zip((definition.numerator, definition.denominator), parts, strict=True)
            if p is None
        ]
        reason = _not_reported(missing, fiscal_year, period)
    elif _period(num) != _period(den):
        reason = (
            f"{definition.numerator} and {definition.denominator} cover different periods"
            f" ({_span(num)} and {_span(den)})"
        )
    elif den.fact.value <= 0:
        reason = f"{definition.denominator} is not positive ({den.fact.value})"
    else:
        scale = 100 if definition.unit == "percent" else 1
        value = (num.fact.value / den.fact.value * scale).quantize(PLACES)
    found = [p for p in parts if p is not None]
    return _result(
        company=company,
        ratio=definition.name,
        label=definition.label,
        formula=definition.formula,
        unit=definition.unit,
        fiscal_year=fiscal_year,
        period=period,
        anchor=den or num,
        value=value,
        reason=reason,
        missing=num is None or den is None,
        inputs=found,
        index_version=index_version,
    )


def growth_result(
    facts: Sequence[LatestFact],
    company: CompanyRef,
    concept: Concept,
    fiscal_year: int,
    period: PeriodRequest,
    index_version: str,
) -> RatioResult:
    """Percent change from the same fiscal period one fiscal year before."""
    prior, current = (
        pick_fact(facts, cik=company.cik, concept=concept, fiscal_year=y, period=period)
        for y in (fiscal_year - 1, fiscal_year)
    )
    value: Decimal | None = None
    reason: str | None = None
    if prior is None or current is None:
        years = [y for y, p in ((fiscal_year - 1, prior), (fiscal_year, current)) if p is None]
        reason = "; ".join(_not_reported([concept.name], y, period) for y in years)
    elif prior.fact.value == 0:
        reason = f"{concept.name} was zero in fiscal {fiscal_year - 1}"
    else:
        change = (current.fact.value - prior.fact.value) / abs(prior.fact.value) * 100
        value = change.quantize(PLACES)
    name, before = concept.name, fiscal_year - 1
    return _result(
        company=company,
        ratio=GROWTH,
        label=f"{concept.label}, change from fiscal {before}",
        formula=f"({name}[{fiscal_year}] - {name}[{before}]) / |{name}[{before}]| * 100",
        unit="percent",
        fiscal_year=fiscal_year,
        period=period,
        anchor=current,
        value=value,
        reason=reason,
        missing=prior is None or current is None,
        inputs=[p for p in (prior, current) if p is not None],
        index_version=index_version,
    )


def _result(
    *,
    company: CompanyRef,
    ratio: str,
    label: str,
    formula: str,
    unit: RatioUnit,
    fiscal_year: int,
    period: PeriodRequest,
    anchor: LatestFact | None,
    value: Decimal | None,
    reason: str | None,
    missing: bool,
    inputs: Sequence[LatestFact],
    index_version: str,
) -> RatioResult:
    status = "computed" if value is not None else "not_reported" if missing else "undefined"
    return RatioResult(
        status=status,
        company=company,
        ratio=ratio,
        label=label,
        formula=formula,
        unit=unit,
        fiscal_year=fiscal_year,
        fiscal_period=period.fiscal_period,
        period_kind=period.kind,
        period_start=None if anchor is None else anchor.fact.period_start,
        period_end=None if anchor is None else anchor.fact.period_end,
        value=value,
        reason=reason,
        inputs=tuple(FactValue.of(x) for x in inputs),
        index_version=index_version,
    )


def _not_reported(names: Sequence[str], fiscal_year: int, period: PeriodRequest) -> str:
    return f"not reported for fiscal {fiscal_year} {period.fiscal_period}: {', '.join(names)}"


def _period(x: LatestFact) -> tuple[dt.date | None, dt.date]:
    return (x.fact.period_start, x.fact.period_end)


def _span(x: LatestFact) -> str:
    start = x.fact.period_start
    return f"{start} to {x.fact.period_end}" if start else f"at {x.fact.period_end}"
