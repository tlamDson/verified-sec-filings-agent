"""What the web app shows of a turn's evidence: metric cards, citations, chart series.

Each model is a narrower view of one tool result. Values stay `Decimal` and are sent as
the exact text the tool returned; nothing here is computed, rounded or converted.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class CompanyTag(BaseModel):
    model_config = _FROZEN

    ticker: str
    name: str


class FilingSource(BaseModel):
    """The filing a value was read from."""

    model_config = _FROZEN

    accession: str
    form: str
    filed: dt.date
    url: str


class FactCard(BaseModel):
    """One reported value (`get_fact`), or the statement that it was not reported (E12)."""

    model_config = _FROZEN

    kind: Literal["fact"] = "fact"
    call_id: str
    company: CompanyTag
    concept: str
    label: str
    unit: str
    fiscal_year: int
    fiscal_period: str
    status: Literal["found", "not_reported"]
    value: Decimal | None
    period_start: dt.date | None
    period_end: dt.date | None
    """The fiscal period's own end date (E1)."""
    source: FilingSource | None
    restated: bool
    """A later filing changed the value; `value` is the latest filed one (E2)."""
    original_value: Decimal | None
    original_filed: dt.date | None


class RatioInput(BaseModel):
    """One reported fact a ratio was computed from."""

    model_config = _FROZEN

    concept: str
    label: str
    value: Decimal
    unit: str
    fiscal_year: int | None
    period_end: dt.date
    source: FilingSource


class RatioCard(BaseModel):
    """A ratio or year-over-year change computed in code (`compute_ratio`)."""

    model_config = _FROZEN

    kind: Literal["ratio"] = "ratio"
    call_id: str
    company: CompanyTag
    ratio: str
    label: str
    formula: str
    unit: str
    fiscal_year: int
    fiscal_period: str
    status: Literal["computed", "not_reported", "undefined"]
    value: Decimal | None
    reason: str | None
    period_start: dt.date | None
    period_end: dt.date | None
    inputs: tuple[RatioInput, ...]


class PeerRow(BaseModel):
    model_config = _FROZEN

    rank: int | None
    company: CompanyTag
    status: Literal["found", "computed", "not_reported", "undefined"]
    value: Decimal | None
    period_end: dt.date | None
    """Each company's own period end; fiscal years are never aligned (E3)."""
    reason: str | None


class PeersCard(BaseModel):
    """One metric across companies, ranked (`compare_peers`)."""

    model_config = _FROZEN

    kind: Literal["peers"] = "peers"
    call_id: str
    metric: str
    label: str
    unit: str
    fiscal_year: int
    fiscal_period: str
    same_period_end: bool
    note: str
    rows: tuple[PeerRow, ...]


class RiskFiling(BaseModel):
    model_config = _FROZEN

    accession: str
    form: str
    filing_date: dt.date
    report_date: dt.date
    fiscal_year: int
    url: str


class RiskChange(BaseModel):
    model_config = _FROZEN

    kind: Literal["added", "removed", "changed"]
    text: str | None
    previous_text: str | None


class RiskDiffCard(BaseModel):
    """Risk factor paragraphs that differ between two 10-Ks (`diff_risk_factors`)."""

    model_config = _FROZEN

    kind: Literal["risk_diff"] = "risk_diff"
    call_id: str
    company: CompanyTag
    status: Literal["compared", "not_found"]
    reason: str | None
    current: RiskFiling | None
    previous: RiskFiling | None
    added: int
    removed: int
    changed: int
    unchanged: int
    changes: tuple[RiskChange, ...]
    changes_total: int


class NoticeCard(BaseModel):
    """A tool refused the request: out of scope (E7), unknown figure (E4), and so on."""

    model_config = _FROZEN

    kind: Literal["notice"] = "notice"
    call_id: str
    tool: str
    code: str
    message: str


Card = Annotated[
    FactCard | RatioCard | PeersCard | RiskDiffCard | NoticeCard, Field(discriminator="kind")
]


class Citation(BaseModel):
    """A source the answer may cite: a passage by its chunk key, or a filing by its
    accession number."""

    model_config = _FROZEN

    key: str
    kind: Literal["passage", "filing"]
    company: CompanyTag | None
    form: str
    section: str | None
    filing_date: dt.date
    report_date: dt.date | None
    text: str | None
    url: str


class EvidenceView(BaseModel):
    model_config = _FROZEN

    cards: tuple[Card, ...]
    citations: tuple[Citation, ...]


class ChartPoint(BaseModel):
    model_config = _FROZEN

    x: str
    """A fiscal period ("FY2024", "Q2 FY2024") or, for peers, a ticker."""
    value: Decimal
    period_end: dt.date | None


class ChartSeries(BaseModel):
    model_config = _FROZEN

    name: str
    points: tuple[ChartPoint, ...]


class Chart(BaseModel):
    model_config = _FROZEN

    kind: Literal["trend", "peers"]
    title: str
    unit: str
    series: tuple[ChartSeries, ...]
