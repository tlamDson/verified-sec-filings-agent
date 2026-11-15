"""get_fact: one company's reported value of one concept for one fiscal period.

A value the company did not report is the answer "not reported" (E12), never an estimate.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.tools.companies import CompanyRef
from sec_agent.tools.context import FactsContext
from sec_agent.tools.fact_value import FactValue
from sec_agent.tools.metrics import require_concept
from sec_agent.tools.periods import FiscalYear, pick_fact, resolve_period
from sec_agent.xbrl.calendar import FiscalPeriod
from sec_agent.xbrl.periods import PeriodKind


class GetFactArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    company: str = Field(min_length=1, max_length=100, description="Ticker, CIK or name.")
    concept: str = Field(min_length=1, max_length=100, description="A canonical concept name.")
    fiscal_year: FiscalYear
    fiscal_period: FiscalPeriod = "FY"
    year_to_date: bool = Field(
        default=False, description="For Q2-Q4 amounts: the fiscal year so far, not the quarter."
    )


class GetFactResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["found", "not_reported"]
    company: CompanyRef
    concept: str
    label: str
    unit: str
    fiscal_year: int
    fiscal_period: FiscalPeriod
    period_kind: PeriodKind
    index_version: str
    fact: FactValue | None


def get_fact(ctx: FactsContext, args: GetFactArgs) -> GetFactResult:
    company = ctx.companies.resolve(args.company)
    concept = require_concept(args.concept)
    period = resolve_period(concept, args.fiscal_period, year_to_date=args.year_to_date)
    facts = ctx.facts.lookup(
        index_version=ctx.index_version,
        ciks=(company.cik,),
        concepts=(concept.name,),
        fiscal_years=(args.fiscal_year,),
    )
    found = pick_fact(
        facts, cik=company.cik, concept=concept, fiscal_year=args.fiscal_year, period=period
    )
    return GetFactResult(
        status="not_reported" if found is None else "found",
        company=company,
        concept=concept.name,
        label=concept.label,
        unit=concept.unit,
        fiscal_year=args.fiscal_year,
        fiscal_period=period.fiscal_period,
        period_kind=period.kind,
        index_version=ctx.index_version,
        fact=None if found is None else FactValue.of(found),
    )
