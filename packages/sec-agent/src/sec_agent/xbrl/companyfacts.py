"""The companyfacts document as SEC serves it, parsed into typed entries.

Shape: `{"cik", "entityName", "facts": {taxonomy: {tag: {"label", "units": {unit: [entry]}}}}}`.
An entry's `fy`, `fp` and `form` describe the filing that reported it, not the entry's own
period: a 10-K repeats prior years as comparatives under its own `fy`.
"""

import datetime as dt
import json
from collections.abc import Iterator
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RawEntry(BaseModel):
    """One reported value: a tag, in one unit, for one period, in one filing."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    start: dt.date | None = None
    end: dt.date
    val: Decimal
    accn: str = Field(min_length=1)
    fy: int | None = None
    fp: str | None = None
    form: str
    filed: dt.date
    frame: str | None = None


class RawTag(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    label: str | None = None
    units: dict[str, list[RawEntry]]


class CompanyFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    cik: int = Field(gt=0)
    entity_name: str = Field(alias="entityName")
    facts: dict[str, dict[str, RawTag]]

    def entries(self) -> Iterator[tuple[str, str, str, RawEntry]]:
        """Every entry as (taxonomy, tag, unit, entry)."""
        for taxonomy, tags in self.facts.items():
            for tag, raw in tags.items():
                for unit, entries in raw.units.items():
                    for entry in entries:
                        yield taxonomy, tag, unit, entry


def parse_companyfacts(body: bytes) -> CompanyFacts:
    """Parse a companyfacts body. Decimals stay exact (EPS 11.93 is not a binary float).

    Raises ValueError (bad JSON) or pydantic.ValidationError (wrong shape).
    """
    data: object = json.loads(body, parse_float=Decimal)
    return CompanyFacts.model_validate(data)
