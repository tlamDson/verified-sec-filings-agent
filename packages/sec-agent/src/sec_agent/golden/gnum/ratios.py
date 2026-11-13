"""Ratio candidates: one fact over another of the same company and period, in percent.

A ratio is asked only when both parts are reported for exactly the same period and the
denominator is positive; nothing is averaged or combined across periods.
"""

from collections.abc import Sequence
from typing import NamedTuple

from sec_agent.golden.gnum import phrasing
from sec_agent.golden.gnum.candidates import (
    PLACES,
    GNumCompany,
    askable,
    fiscal_label,
    make_question,
    number,
)
from sec_agent.golden.gnum.models import NumQuestion


class Ratio(NamedTuple):
    label: str
    numerator: str
    denominator: str


RATIOS: dict[str, Ratio] = {
    "gross_margin": Ratio("gross margin", "gross_profit", "revenue"),
    "operating_margin": Ratio("operating margin", "operating_income", "revenue"),
    "net_margin": Ratio("net margin", "net_income", "revenue"),
    "effective_tax_rate": Ratio("effective tax rate", "income_tax", "pretax_income"),
}


def ratio_questions(
    company: GNumCompany, *, years: Sequence[int], index_version: str
) -> list[NumQuestion]:
    facts = askable(company, years)
    by_period = {
        (x.fact.concept, x.fact.unit, x.fact.period_start, x.fact.period_end): x for x in facts
    }
    out: list[NumQuestion] = []
    for name, ratio in RATIOS.items():
        for den in facts:
            d = den.fact
            if d.concept != ratio.denominator or d.value <= 0:
                continue
            num = by_period.get((ratio.numerator, d.unit, d.period_start, d.period_end))
            if num is None:
                continue
            fy, fp = fiscal_label(d)
            text = phrasing.ratio_question(company.company, ratio.label, d.period_kind, fy, fp)
            out.append(
                make_question(
                    company=company.company,
                    qtype="ratio",
                    name=name,
                    text=text,
                    current=d,
                    answer=number((num.fact.value / d.value * 100).quantize(PLACES), "percent", d),
                    sources=(num, den),
                    index_version=index_version,
                )
            )
    return out
