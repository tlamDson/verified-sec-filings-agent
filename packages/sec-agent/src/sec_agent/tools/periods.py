"""From a request (concept, fiscal period, year-to-date) to the stored period it means.

Facts are labelled by their own period end (`sec_agent.xbrl.calendar`), so a request is
always in the company's fiscal calendar (E1), never the calendar year:

- A balance (instant) at the end of Q4 is the fiscal year-end balance, labelled FY; a
  balance has no year-to-date.
- An amount (duration) for FY is the annual period. For Q1 to Q4 it is the three months,
  unless year-to-date is asked: Q1 year-to-date is the quarter, Q2 and Q3 are six and nine
  months (`ytd`), and Q4 year-to-date is the fiscal year.
"""

from collections.abc import Sequence
from typing import Annotated, NamedTuple

from pydantic import Field

from sec_agent.tools.errors import AmbiguousFactError, InvalidRequestError
from sec_agent.xbrl.calendar import FiscalPeriod
from sec_agent.xbrl.concepts import Concept
from sec_agent.xbrl.periods import PeriodKind
from sec_agent.xbrl.versions import LatestFact

FiscalYear = Annotated[
    int, Field(ge=1990, le=2100, description="The company's own fiscal year, not the calendar.")
]


class PeriodRequest(NamedTuple):
    kind: PeriodKind
    fiscal_period: FiscalPeriod


def resolve_period(
    concept: Concept, fiscal_period: FiscalPeriod, *, year_to_date: bool = False
) -> PeriodRequest:
    if concept.period_type == "instant":
        if year_to_date:
            raise InvalidRequestError(f"{concept.name} is a balance; it has no year-to-date")
        return PeriodRequest("instant", "FY" if fiscal_period == "Q4" else fiscal_period)
    match fiscal_period:
        case "FY":
            return PeriodRequest("annual", "FY")
        case "Q4" if year_to_date:
            return PeriodRequest("annual", "FY")
        case "Q2" | "Q3" if year_to_date:
            return PeriodRequest("ytd", fiscal_period)
        case _:
            return PeriodRequest("quarter", fiscal_period)


def pick_fact(
    facts: Sequence[LatestFact],
    *,
    cik: int,
    concept: Concept,
    fiscal_year: int,
    period: PeriodRequest,
) -> LatestFact | None:
    """The one fact of this company, concept (in its unit), fiscal year and period, if any."""
    matches = [
        x
        for x in facts
        if x.fact.cik == cik
        and x.fact.concept == concept.name
        and x.fact.unit == concept.unit
        and x.fact.fiscal_year == fiscal_year
        and x.fact.fiscal_period == period.fiscal_period
        and x.fact.period_kind == period.kind
    ]
    if len(matches) > 1:
        ends = ", ".join(sorted(str(x.fact.period_end) for x in matches))
        raise AmbiguousFactError(
            f"{concept.name} of CIK {cik} has {len(matches)} periods labelled "
            f"{fiscal_year} {period.fiscal_period} ({ends})"
        )
    return matches[0] if matches else None
