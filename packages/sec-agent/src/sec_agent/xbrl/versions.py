"""Restated figures (E2): of all filed versions of a value, the latest filed one wins.

"Latest" is the greatest (filed date, accession number); the accession breaks ties
between filings made on the same day. The earliest version is kept as the original, and
`restated` says whether any version's value differs. A change of precision (thousands in
one filing, millions in a later one) counts as a difference: the original value is there
for whoever shows the figure to judge. The `facts_latest` view in `schema.sql` applies
the same rule in SQL; a test holds the two to the same answer.
"""

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.xbrl.models import Fact, SeriesKey


class LatestFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact: Fact
    """The latest filed version."""
    original_value: Decimal
    original_accession: str
    original_filed: dt.date
    versions: int = Field(ge=1)
    restated: bool


def _filing_order(f: Fact) -> tuple[dt.date, str]:
    return (f.filed, f.accession)


def latest_versions(facts: Iterable[Fact]) -> list[LatestFact]:
    """One LatestFact per (concept, unit, period), in the order the series first appear."""
    series: defaultdict[SeriesKey, list[Fact]] = defaultdict(list)
    for fact in facts:
        series[fact.series_key].append(fact)
    out: list[LatestFact] = []
    for versions in series.values():
        ordered = sorted(versions, key=_filing_order)
        original, latest = ordered[0], ordered[-1]
        out.append(
            LatestFact(
                fact=latest,
                original_value=original.value,
                original_accession=original.accession,
                original_filed=original.filed,
                versions=len(ordered),
                restated=len({v.value for v in ordered}) > 1,
            )
        )
    return out
