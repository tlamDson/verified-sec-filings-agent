"""Single-company G-num candidates: a reported value, or its change from a year before.

A fact is asked about only when it has a fiscal label, falls in the configured fiscal years,
and is a full year, a quarter, or a balance at a period end (year-to-date sums are left
out). Each fact is the latest filed version (E2); the source keeps the original value.

A value question is a `fiscal_period` trap (E1) when the period does not lie inside the
calendar year its fiscal year names: Apple's fiscal 2023 began in September 2022, NVIDIA's
first quarter of fiscal 2025 ended in April 2024. Otherwise it is a plain `value` question.
"""

import hashlib
import json
from collections.abc import Iterable, Sequence
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from sec_agent.golden.gnum import phrasing
from sec_agent.golden.gnum.models import (
    AnswerUnit,
    NumberAnswer,
    NumQuestion,
    QuestionType,
    SourceFact,
)
from sec_agent.golden.split import SplitCompany
from sec_agent.xbrl.calendar import FiscalPeriod
from sec_agent.xbrl.concepts import concept
from sec_agent.xbrl.models import Fact
from sec_agent.xbrl.versions import LatestFact

ASKED_KINDS = frozenset({"annual", "quarter", "instant"})
PLACES = Decimal("0.000001")
"""Computed answers (growth, ratios) are rounded half-even to six decimal places."""


class GNumCompany(BaseModel):
    """One company of the split and its latest facts in one index version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    company: SplitCompany
    facts: tuple[LatestFact, ...]


def question_id(*parts: object) -> str:
    """Stable id from what the question asks, independent of seed and selection."""
    digest = hashlib.sha256(json.dumps([str(p) for p in parts]).encode("utf-8")).hexdigest()
    return f"gnum-{digest[:16]}"


def askable(company: GNumCompany, years: Sequence[int]) -> list[LatestFact]:
    """Facts with a fiscal label, inside `years`, of an asked period kind."""
    return [
        x
        for x in company.facts
        if x.fact.fiscal_year in years
        and x.fact.fiscal_period is not None
        and x.fact.period_kind in ASKED_KINDS
    ]


def is_fiscal_period_trap(fact: Fact) -> bool:
    start = fact.period_start or fact.period_end
    return start.year != fact.fiscal_year or fact.period_end.year != fact.fiscal_year


def fiscal_label(fact: Fact) -> tuple[int, FiscalPeriod]:
    """The fact's fiscal year and period; ValueError for an unlabelled fact."""
    if fact.fiscal_year is None or fact.fiscal_period is None:
        raise ValueError("a question needs a fact with a fiscal label")
    return fact.fiscal_year, fact.fiscal_period


def number(value: Decimal, unit: AnswerUnit, fact: Fact) -> NumberAnswer:
    return NumberAnswer(
        value=value, unit=unit, period_start=fact.period_start, period_end=fact.period_end
    )


def _unit(fact: Fact) -> AnswerUnit:
    match fact.unit:
        case "USD" | "USD/shares" | "shares":
            return fact.unit
        case other:
            raise ValueError(f"no answer unit for {other!r}")


def make_question(
    *,
    company: SplitCompany,
    qtype: QuestionType,
    name: str,
    text: str,
    current: Fact,
    answer: NumberAnswer,
    sources: Iterable[LatestFact],
    index_version: str,
) -> NumQuestion:
    """A single-company question about `current`'s period."""
    fy, fp = fiscal_label(current)
    period = (current.unit, current.period_start, current.period_end)
    return NumQuestion(
        id=question_id(qtype, company.cik, name, *period),
        split=company.split,
        qtype=qtype,
        question=text,
        tickers=(company.ticker,),
        ciks=(company.cik,),
        concept=name,
        fiscal_year=fy,
        fiscal_period=fp,
        period_kind=current.period_kind,
        answer=answer,
        sources=tuple(SourceFact.of(s) for s in sources),
        index_version=index_version,
    )


def value_questions(
    company: GNumCompany, *, years: Sequence[int], index_version: str
) -> list[NumQuestion]:
    """One `value` or `fiscal_period` question per askable fact."""
    out: list[NumQuestion] = []
    for latest in askable(company, years):
        f = latest.fact
        fy, fp = fiscal_label(f)
        text = phrasing.value_question(
            company.company, concept(f.concept).label, f.period_kind, fy, fp
        )
        out.append(
            make_question(
                company=company.company,
                qtype="fiscal_period" if is_fiscal_period_trap(f) else "value",
                name=f.concept,
                text=text,
                current=f,
                answer=number(f.value, _unit(f), f),
                sources=(latest,),
                index_version=index_version,
            )
        )
    return out


def growth_questions(
    company: GNumCompany, *, years: Sequence[int], index_version: str
) -> list[NumQuestion]:
    """Percent change from the same fiscal period one year before (a balance: year end only)."""
    by_label = {
        (
            x.fact.concept,
            x.fact.unit,
            x.fact.period_kind,
            x.fact.fiscal_year,
            x.fact.fiscal_period,
        ): x
        for x in company.facts
        if x.fact.fiscal_period is not None and x.fact.period_kind in ASKED_KINDS
    }
    out: list[NumQuestion] = []
    for current in askable(company, years):
        f = current.fact
        fy, fp = fiscal_label(f)
        if f.period_kind == "instant" and fp != "FY":
            continue
        key = (f.concept, f.unit, f.period_kind, fy - 1, fp)
        prior = by_label.get(key)
        if prior is None or prior.fact.value == 0:
            continue
        change = (f.value - prior.fact.value) / abs(prior.fact.value) * 100
        text = phrasing.growth_question(
            company.company, concept(f.concept).label, f.period_kind, fy, fp
        )
        out.append(
            make_question(
                company=company.company,
                qtype="yoy_growth",
                name=f.concept,
                text=text,
                current=f,
                answer=number(change.quantize(PLACES), "percent", f),
                sources=(prior, current),
                index_version=index_version,
            )
        )
    return out
