"""Question text from fixed templates: a period is always named in the company's fiscal terms."""

from sec_agent.golden.split import SplitCompany
from sec_agent.xbrl.calendar import FiscalPeriod
from sec_agent.xbrl.periods import PeriodKind

_QUARTERS = {"Q1": "first", "Q2": "second", "Q3": "third", "Q4": "fourth"}


def company_name(company: SplitCompany) -> str:
    return f"{company.name} ({company.ticker})"


def lower_label(label: str) -> str:
    """'Revenue' -> 'revenue'; keeps the rest of the label as the concept table writes it."""
    return label[:1].lower() + label[1:]


def period_phrase(kind: PeriodKind, fy: int, fp: FiscalPeriod) -> str:
    """'fiscal year 2023', 'the first quarter of fiscal year 2024'."""
    year = f"fiscal year {fy}"
    if fp == "FY" or kind == "annual":
        return year
    return f"the {_QUARTERS[fp]} quarter of {year}"


def when(kind: PeriodKind, fy: int, fp: FiscalPeriod) -> str:
    """'for fiscal year 2023', or 'at the end of fiscal year 2023' for a balance."""
    phrase = period_phrase(kind, fy, fp)
    return f"at the end of {phrase}" if kind == "instant" else f"for {phrase}"


def value_question(
    company: SplitCompany, label: str, kind: PeriodKind, fy: int, fp: FiscalPeriod
) -> str:
    return f"What did {company_name(company)} report as {lower_label(label)} {when(kind, fy, fp)}?"


def growth_question(
    company: SplitCompany, label: str, kind: PeriodKind, fy: int, fp: FiscalPeriod
) -> str:
    start = period_phrase(kind, fy - 1, fp)
    end = period_phrase(kind, fy, fp)
    if kind == "instant":
        start, end = f"the end of {start}", f"the end of {end}"
    return (
        f"By what percentage did the {lower_label(label)} of {company_name(company)} change "
        f"from {start} to {end}?"
    )


def ratio_question(
    company: SplitCompany, label: str, kind: PeriodKind, fy: int, fp: FiscalPeriod
) -> str:
    return f"What was the {label} of {company_name(company)} {when(kind, fy, fp)}, in percent?"


def peer_question(
    first: SplitCompany, second: SplitCompany, label: str, kind: PeriodKind, fy: int
) -> str:
    own = f"its own fiscal year {fy}"
    period = f"at the end of {own}" if kind == "instant" else f"for {own}"
    return (
        f"Which company reported the higher {lower_label(label)} {period}: "
        f"{company_name(first)} or {company_name(second)}?"
    )
