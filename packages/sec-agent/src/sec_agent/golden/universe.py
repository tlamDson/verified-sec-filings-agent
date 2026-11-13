"""The company universe: S&P 100 constituents with their GICS sector and SEC CIK.

`sp100.csv` holds one row per company (Alphabet's two share classes are one company, CIK
1652044). Membership and sectors come from the S&P 100 components table on Wikipedia as of
2026-09-21. CIKs come from SEC's `company_tickers.json` and `fiscal_year_end` (MMDD, the
current fiscal year's end) from each company's `submissions` document, both fetched through
`EdgarClient` on 2026-11-13. A company with no 10-K for part of fiscal 2020-2024 carries an
`excluded` reason and is never sampled.
"""

import csv
import hashlib
import json
from collections.abc import Iterable
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

GicsSector = Literal[
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
]
GICS_SECTORS: tuple[GicsSector, ...] = GicsSector.__args__  # pyright: ignore[reportAttributeAccessIssue]


class Company(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.]*$")
    name: str = Field(min_length=1)
    sector: GicsSector
    cik: int = Field(gt=0)
    fiscal_year_end: str = Field(default="1231", pattern=r"^(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$")
    excluded: str = ""
    """Why the company is never sampled; empty when it is eligible."""

    @property
    def off_calendar(self) -> bool:
        """The fiscal year does not end near December 31 (E1): Apple's September, NVIDIA's
        January. A 52/53-week year ending December 25 to January 7 counts as calendar."""
        return "0108" <= self.fiscal_year_end <= "1224"


def load_universe(path: Path | None = None) -> tuple[Company, ...]:
    """Read the universe CSV (default: the packaged `sp100.csv`); tickers and CIKs unique."""
    text = (
        files("sec_agent.golden").joinpath("sp100.csv").read_text("utf-8")
        if path is None
        else path.read_text("utf-8")
    )
    companies = tuple(Company.model_validate(row) for row in csv.DictReader(text.splitlines()))
    for field in ("ticker", "cik"):
        values = [getattr(c, field) for c in companies]
        if len(set(values)) != len(values):
            raise ValueError(f"universe has a duplicate {field.upper()}")
    return companies


def universe_digest(companies: Iterable[Company]) -> str:
    """SHA-256 of the companies in CIK order: a split records which universe it came from."""
    rows = [c.model_dump(mode="json") for c in sorted(companies, key=lambda c: c.cik)]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()
