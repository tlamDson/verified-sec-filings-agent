"""compare_peers: one concept or ratio for several companies, ranked, from one facts query.

Each company is read on its own fiscal year (E3): Apple's fiscal 2024 ended in September
2024, NVIDIA's in January 2024. Nothing is converted to calendar years; every row carries
its period end, and `same_period_end` says whether the periods line up. A company that did
not report the value is listed without a rank (E12). Equal values share a rank.
"""

import datetime as dt
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sec_agent.tools.companies import CompanyRef
from sec_agent.tools.context import FactsContext
from sec_agent.tools.errors import InvalidRequestError
from sec_agent.tools.fact_value import FactValue
from sec_agent.tools.metrics import require_concept
from sec_agent.tools.periods import FiscalYear, pick_fact, resolve_period
from sec_agent.tools.ratio_defs import GROWTH, RATIOS
from sec_agent.tools.ratios import ratio_result, require_ratio
from sec_agent.xbrl.calendar import FiscalPeriod
from sec_agent.xbrl.concepts import CONCEPTS
from sec_agent.xbrl.periods import PeriodKind

MAX_PEERS = 10
NOTE = (
    "Each company is compared on its own fiscal year; fiscal years can end in different "
    "months, so compare the period end dates before reading the ranking as same-period."
)
_CONCEPT_NAMES = frozenset(c.name for c in CONCEPTS)


class ComparePeersArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    companies: tuple[str, ...] = Field(
        default=(), max_length=MAX_PEERS, description="Two to ten tickers, CIKs or names."
    )
    peers_of: str | None = Field(
        default=None, max_length=100, description="Instead: this company's GICS sector."
    )
    metric: str = Field(min_length=1, max_length=100, description="A concept or ratio name.")
    fiscal_year: FiscalYear
    fiscal_period: FiscalPeriod = "FY"
    year_to_date: bool = False

    @model_validator(mode="after")
    def _one_list(self) -> Self:
        if (self.peers_of is None) == (not self.companies):
            raise ValueError("give either companies or peers_of, not both")
        if self.companies and len(self.companies) < 2:
            raise ValueError("compare at least two companies")
        return self


class PeerRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rank: int | None
    company: CompanyRef
    status: Literal["found", "computed", "not_reported", "undefined"]
    value: Decimal | None
    period_start: dt.date | None
    period_end: dt.date | None
    reason: str | None
    inputs: tuple[FactValue, ...]


class PeerComparison(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str
    metric_kind: Literal["concept", "ratio"]
    label: str
    unit: str
    fiscal_year: int
    fiscal_period: FiscalPeriod
    period_kind: PeriodKind
    rows: tuple[PeerRow, ...]
    same_period_end: bool
    note: str
    index_version: str


def compare_peers(ctx: FactsContext, args: ComparePeersArgs) -> PeerComparison:
    companies = _companies(ctx, args)
    ciks = tuple(c.cik for c in companies)
    if args.metric == GROWTH:
        raise InvalidRequestError(f"{GROWTH} is not a peer metric; use compute_ratio per company")
    if args.metric in _CONCEPT_NAMES:
        concept = require_concept(args.metric)
        period = resolve_period(concept, args.fiscal_period, year_to_date=args.year_to_date)
        names: tuple[str, ...] = (concept.name,)
        kind: Literal["concept", "ratio"] = "concept"
        label, unit = concept.label, concept.unit
    else:
        definition = require_ratio(args.metric)
        period = resolve_period(
            require_concept(definition.denominator),
            args.fiscal_period,
            year_to_date=args.year_to_date,
        )
        names, kind = (definition.numerator, definition.denominator), "ratio"
        label, unit = definition.label, definition.unit
    facts = ctx.facts.lookup(
        index_version=ctx.index_version, ciks=ciks, concepts=names, fiscal_years=(args.fiscal_year,)
    )
    rows: list[PeerRow] = []
    for company in companies:
        if kind == "concept":
            found = pick_fact(
                facts,
                cik=company.cik,
                concept=require_concept(names[0]),
                fiscal_year=args.fiscal_year,
                period=period,
            )
            rows.append(
                PeerRow(
                    rank=None,
                    company=company,
                    status="not_reported" if found is None else "found",
                    value=None if found is None else found.fact.value,
                    period_start=None if found is None else found.fact.period_start,
                    period_end=None if found is None else found.fact.period_end,
                    reason=None if found is not None else "not reported",
                    inputs=() if found is None else (FactValue.of(found),),
                )
            )
        else:
            r = ratio_result(
                facts, company, RATIOS[args.metric], args.fiscal_year, period, ctx.index_version
            )
            rows.append(
                PeerRow(
                    rank=None,
                    company=company,
                    status=r.status,
                    value=r.value,
                    period_start=r.period_start,
                    period_end=r.period_end,
                    reason=r.reason,
                    inputs=r.inputs,
                )
            )
    ranked = _rank(rows)
    ends = {r.period_end for r in ranked if r.value is not None}
    return PeerComparison(
        metric=args.metric,
        metric_kind=kind,
        label=label,
        unit=unit,
        fiscal_year=args.fiscal_year,
        fiscal_period=period.fiscal_period,
        period_kind=period.kind,
        rows=ranked,
        same_period_end=len(ends) <= 1,
        note=NOTE,
        index_version=ctx.index_version,
    )


def _companies(ctx: FactsContext, args: ComparePeersArgs) -> tuple[CompanyRef, ...]:
    if args.peers_of is not None:
        return ctx.companies.sector_peers(ctx.companies.resolve(args.peers_of))
    refs = [ctx.companies.resolve(text) for text in args.companies]
    seen: set[int] = set()
    for ref in refs:
        if ref.cik in seen:
            raise InvalidRequestError(f"{ref.ticker} is named twice")
        seen.add(ref.cik)
    return tuple(refs)


def _rank(rows: list[PeerRow]) -> tuple[PeerRow, ...]:
    """Highest value first, ties by ticker and sharing a rank (1, 1, 3); no value last."""
    valued = sorted(
        (r for r in rows if r.value is not None),
        key=lambda r: (-(r.value or Decimal(0)), r.company.ticker),
    )
    out: list[PeerRow] = []
    for i, row in enumerate(valued):
        same = out and out[-1].value == row.value
        rank = out[-1].rank if same else i + 1
        out.append(row.model_copy(update={"rank": rank}))
    return (*out, *(r for r in rows if r.value is None))
