"""A normalised fact (one filed version of one value) and the normalisation report."""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.xbrl.calendar import FiscalPeriod
from sec_agent.xbrl.periods import PeriodKind

SeriesKey = tuple[str, str, dt.date | None, dt.date]
"""(concept, unit, period_start, period_end): one value over time, across filings."""
VersionKey = tuple[str, str, dt.date | None, dt.date, str]
"""A series key plus the accession number: one filed version of that value."""


class Fact(BaseModel):
    """One canonical concept, in one unit, for one period, as one filing reported it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cik: int = Field(gt=0)
    concept: str
    unit: str
    period_kind: PeriodKind
    period_start: dt.date | None
    period_end: dt.date
    fiscal_year: int | None
    fiscal_period: FiscalPeriod | None
    value: Decimal
    taxonomy: str
    tag: str
    accession: str
    form: str
    filed: dt.date
    frame: str | None = None

    @property
    def series_key(self) -> SeriesKey:
        return (self.concept, self.unit, self.period_start, self.period_end)

    @property
    def version_key(self) -> VersionKey:
        return (*self.series_key, self.accession)


class NormalizationReport(BaseModel):
    """What normalisation kept and why it dropped the rest. Counts entries of table tags."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entries_seen: int = 0
    facts_kept: int = 0
    form_out_of_scope: int = 0
    """Entries from filings other than 10-K, 10-K/A, 10-Q, 10-Q/A (8-K, S-1, ...)."""
    unit_mismatch: int = 0
    """Entries in a unit other than the concept's (E5): never converted."""
    period_type_mismatch: int = 0
    """A duration concept without a start date, or an instant with one."""
    unsupported_duration: int = 0
    """Durations that are not a quarter, six or nine months, or a year."""
    conflicting_values: int = 0
    """Entries dropped because one filing reported two values for one tag and period."""
    lower_priority_tag: int = 0
    """Entries dropped because a preferred tag of the same concept covered the period."""
    unlabelled: int = 0
    """Facts kept without a fiscal label: their end is no fiscal period end on record."""
    fiscal_years_relabelled: int = 0
    """Fiscal year ends whose reported `fy` was corrected (see `calendar`)."""
