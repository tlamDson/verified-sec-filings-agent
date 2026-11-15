"""FactValue: one XBRL value as a tool returns it, with everything a citation needs."""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from sec_agent.edgar.urls import archive_url
from sec_agent.xbrl.calendar import FiscalPeriod
from sec_agent.xbrl.concepts import concept
from sec_agent.xbrl.periods import PeriodKind
from sec_agent.xbrl.versions import LatestFact


class FactValue(BaseModel):
    """The latest filed version of one value (E2), its exact period (E1) and unit (E5).

    `original_*` is the first filed version; `restated` says whether any version differs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cik: int
    concept: str
    label: str
    value: Decimal
    unit: str
    period_kind: PeriodKind
    period_start: dt.date | None
    period_end: dt.date
    fiscal_year: int | None
    fiscal_period: FiscalPeriod | None
    accession: str
    form: str
    filed: dt.date
    taxonomy: str
    tag: str
    filing_url: str
    restated: bool
    original_value: Decimal
    original_accession: str
    original_filed: dt.date
    versions: int

    @classmethod
    def of(cls, latest: LatestFact) -> "FactValue":
        f = latest.fact
        return cls(
            cik=f.cik,
            concept=f.concept,
            label=concept(f.concept).label,
            value=f.value,
            unit=f.unit,
            period_kind=f.period_kind,
            period_start=f.period_start,
            period_end=f.period_end,
            fiscal_year=f.fiscal_year,
            fiscal_period=f.fiscal_period,
            accession=f.accession,
            form=f.form,
            filed=f.filed,
            taxonomy=f.taxonomy,
            tag=f.tag,
            filing_url=archive_url(f.cik, f.accession, f"{f.accession}-index.htm"),
            restated=latest.restated,
            original_value=latest.original_value,
            original_accession=latest.original_accession,
            original_filed=latest.original_filed,
            versions=latest.versions,
        )
