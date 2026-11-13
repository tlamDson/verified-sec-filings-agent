"""A G-num question: its text, the deterministic answer, and the facts the answer comes from."""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from sec_agent.golden.split import CompanySplitName
from sec_agent.xbrl.calendar import FiscalPeriod
from sec_agent.xbrl.periods import PeriodKind
from sec_agent.xbrl.versions import LatestFact

QuestionType = Literal["value", "yoy_growth", "ratio", "peer_comparison", "fiscal_period"]
AnswerUnit = Literal["USD", "USD/shares", "shares", "percent"]

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class SourceFact(BaseModel):
    """One XBRL fact an answer is computed from: the latest filed version, and the original."""

    model_config = _FROZEN

    cik: int
    concept: str
    unit: str
    period_start: dt.date | None
    period_end: dt.date
    fiscal_year: int
    fiscal_period: FiscalPeriod
    value: Decimal
    accession: str
    filed: dt.date
    restated: bool
    original_value: Decimal

    @classmethod
    def of(cls, latest: LatestFact) -> "SourceFact":
        f = latest.fact
        if f.fiscal_year is None or f.fiscal_period is None:
            raise ValueError("only facts with a fiscal label can be a question's source")
        return cls(
            cik=f.cik,
            concept=f.concept,
            unit=f.unit,
            period_start=f.period_start,
            period_end=f.period_end,
            fiscal_year=f.fiscal_year,
            fiscal_period=f.fiscal_period,
            value=f.value,
            accession=f.accession,
            filed=f.filed,
            restated=latest.restated,
            original_value=latest.original_value,
        )


class NumberAnswer(BaseModel):
    """A number in a unit, for the period it covers (an instant has no start)."""

    model_config = _FROZEN

    kind: Literal["number"] = "number"
    value: Decimal
    unit: AnswerUnit
    period_start: dt.date | None
    period_end: dt.date


class CompanyAnswer(BaseModel):
    """The company a peer comparison names."""

    model_config = _FROZEN

    kind: Literal["company"] = "company"
    ticker: str
    cik: int


Answer = Annotated[NumberAnswer | CompanyAnswer, Field(discriminator="kind")]


class NumQuestion(BaseModel):
    model_config = _FROZEN

    id: str = Field(pattern=r"^gnum-[0-9a-f]{16}$")
    split: CompanySplitName
    qtype: QuestionType
    question: str
    tickers: tuple[str, ...]
    ciks: tuple[int, ...]
    concept: str
    """The canonical XBRL concept, or the ratio's name."""
    fiscal_year: int
    fiscal_period: FiscalPeriod
    period_kind: PeriodKind
    answer: Answer
    sources: tuple[SourceFact, ...]
    index_version: str
