"""A company's fiscal calendar: which period end dates are fiscal year and quarter ends (E1).

companyfacts tags each entry with the `fy`/`fp` of the filing that carried it, so a 10-K
for FY2024 labels its FY2023 comparative "fy 2024". The calendar instead learns, from each
10-K and 10-Q, the filing's own period, and labels any fact by its own end date:

1. A filing's own period end is the latest end date among its durations of the filing's
   length (a year for 10-K, a quarter for 10-Q) that carries more than half as many facts
   as the busiest end date. Comparatives carry about as many facts as the own period
   (Apple's FY2009 10-K has two more for FY2008 than for FY2009), so the latest of them
   wins; a stray forward-dated fact (a dividend declared for the next quarter) never does.
2. A fiscal year end takes the `fy` most filings with that own period report.
3. The offset between `fy` and the year the fiscal year ends in (an end on January 1-14
   counts for the year before, for 52/53-week years ending near New Year) is a company
   constant. When one offset holds for a strict majority of fiscal year ends, the ends
   that break it are relabelled with it, and listed. NVIDIA's 10-Ks for the years ended
   January 2012 to January 2014 say `fy` one less than every later one, and than NVIDIA's
   own name for those years ("fiscal 2014" ended 2014-01-26).
4. A quarter takes the fiscal year of the fiscal year end that follows it within a year;
   while that year has not ended, the year after the one before it; failing both, its
   filings' `fy`.
"""

import datetime as dt
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, NamedTuple, Self

from sec_agent.xbrl.companyfacts import CompanyFacts, RawEntry
from sec_agent.xbrl.periods import DurationClass, classify_duration

FiscalPeriod = Literal["FY", "Q1", "Q2", "Q3", "Q4"]
ANNUAL_FORMS = frozenset({"10-K", "10-K/A"})
QUARTERLY_FORMS = frozenset({"10-Q", "10-Q/A"})
FORMS_IN_SCOPE = ANNUAL_FORMS | QUARTERLY_FORMS
_QUARTERS: frozenset[str] = frozenset({"Q1", "Q2", "Q3"})
_YEAR = dt.timedelta(days=380)
_NEW_YEAR_SLACK = dt.timedelta(days=14)


class FiscalLabel(NamedTuple):
    fiscal_year: int
    fiscal_period: FiscalPeriod


@dataclass
class _Filing:
    form: str
    fy: int | None
    fp: str | None
    filed: dt.date
    ends: Counter[dt.date]

    def own_end(self) -> dt.date | None:
        if not self.ends:
            return None
        top = max(self.ends.values())
        return max(end for end, n in self.ends.items() if 2 * n > top)


@dataclass(frozen=True)
class FiscalCalendar:
    annual: Mapping[dt.date, int]
    """Fiscal year end -> fiscal year."""
    quarters: Mapping[dt.date, FiscalLabel]
    """End of a first, second or third quarter -> its label."""
    relabelled: tuple[dt.date, ...] = ()
    """Fiscal year ends whose reported `fy` was corrected (rule 3)."""

    @classmethod
    def from_document(cls, doc: CompanyFacts) -> Self:
        return cls.build(entry for _, _, _, entry in doc.entries())

    @classmethod
    def build(cls, entries: Iterable[RawEntry]) -> Self:
        filings = _filings(entries)
        annual_votes: defaultdict[dt.date, Counter[int]] = defaultdict(Counter)
        quarter_votes: defaultdict[dt.date, Counter[tuple[int, str]]] = defaultdict(Counter)
        for filing in sorted(filings.values(), key=lambda f: f.filed):
            end = filing.own_end()
            if end is None or filing.fy is None:
                continue
            if filing.form in ANNUAL_FORMS and filing.fp == "FY":
                annual_votes[end][filing.fy] += 1
            elif filing.form in QUARTERLY_FORMS and filing.fp in _QUARTERS:
                quarter_votes[end][(filing.fy, filing.fp)] += 1
        annual = {end: votes.most_common(1)[0][0] for end, votes in sorted(annual_votes.items())}
        relabelled = _fix_off_offset_years(annual)
        quarters = {
            end: _quarter_label(end, votes.most_common(1)[0][0], annual)
            for end, votes in sorted(quarter_votes.items())
        }
        return cls(annual=annual, quarters=quarters, relabelled=relabelled)

    def label(self, kind: DurationClass | Literal["instant"], end: dt.date) -> FiscalLabel | None:
        """The fiscal label of a period of `kind` ending on `end`, or None if not a known end."""
        year = self.annual.get(end)
        quarter = self.quarters.get(end)
        match kind:
            case "annual":
                return None if year is None else FiscalLabel(year, "FY")
            case "quarter":
                return FiscalLabel(year, "Q4") if year is not None else quarter
            case "six_months":
                return quarter if quarter is not None and quarter.fiscal_period == "Q2" else None
            case "nine_months":
                return quarter if quarter is not None and quarter.fiscal_period == "Q3" else None
            case "instant":
                return FiscalLabel(year, "FY") if year is not None else quarter


def _filings(entries: Iterable[RawEntry]) -> dict[str, _Filing]:
    filings: dict[str, _Filing] = {}
    for e in entries:
        if e.form not in FORMS_IN_SCOPE:
            continue
        filing = filings.get(e.accn)
        if filing is None:
            filing = filings[e.accn] = _Filing(e.form, e.fy, e.fp, e.filed, Counter())
        if e.start is None:
            continue
        want = "annual" if e.form in ANNUAL_FORMS else "quarter"
        if classify_duration(e.start, e.end) == want:
            filing.ends[e.end] += 1
    return filings


def _anchor_year(end: dt.date) -> int:
    return (end - _NEW_YEAR_SLACK).year


def _fix_off_offset_years(annual: dict[dt.date, int]) -> tuple[dt.date, ...]:
    """Rule 3, in place on `annual`; returns the ends that were relabelled."""
    if not annual:
        return ()
    offset, n = Counter(fy - _anchor_year(end) for end, fy in annual.items()).most_common(1)[0]
    if 2 * n <= len(annual):
        return ()
    fixed: list[dt.date] = []
    for end, fy in sorted(annual.items()):
        expected = _anchor_year(end) + offset
        if fy != expected:
            annual[end] = expected
            fixed.append(end)
    return tuple(fixed)


def _quarter_label(
    end: dt.date, reported: tuple[int, str], annual: Mapping[dt.date, int]
) -> FiscalLabel:
    fy, fp = reported
    following = [e for e in annual if end < e <= end + _YEAR]
    preceding = [e for e in annual if end - _YEAR <= e < end]
    if following:
        fy = annual[min(following)]
    elif preceding:
        fy = annual[max(preceding)] + 1
    match fp:
        case "Q1":
            return FiscalLabel(fy, "Q1")
        case "Q2":
            return FiscalLabel(fy, "Q2")
        case _:
            return FiscalLabel(fy, "Q3")
