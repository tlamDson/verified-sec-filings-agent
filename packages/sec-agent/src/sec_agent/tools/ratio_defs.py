"""The ratios `compute_ratio` knows: one concept over another of the same company and period.

Every part is a reported XBRL concept of the same period type and unit, so a ratio never
mixes a balance with a flow or averages balances across periods. Percent ratios are x 100.
`GROWTH` is the year-over-year change of one concept, asked with that concept.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

RatioUnit = Literal["percent", "times"]
GROWTH = "yoy_growth"
PLACES_TEXT = "0.000001"
"""Computed values are rounded half-even to six decimal places, as the G-num answers are."""


class RatioDef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    label: str
    numerator: str
    denominator: str
    unit: RatioUnit

    @property
    def formula(self) -> str:
        suffix = " * 100" if self.unit == "percent" else ""
        return f"{self.numerator} / {self.denominator}{suffix}"


def _r(name: str, label: str, numerator: str, denominator: str, unit: RatioUnit) -> RatioDef:
    return RatioDef(name=name, label=label, numerator=numerator, denominator=denominator, unit=unit)


RATIOS: dict[str, RatioDef] = {
    r.name: r
    for r in (
        _r("gross_margin", "Gross margin", "gross_profit", "revenue", "percent"),
        _r("operating_margin", "Operating margin", "operating_income", "revenue", "percent"),
        _r("net_margin", "Net margin", "net_income", "revenue", "percent"),
        _r("effective_tax_rate", "Effective tax rate", "income_tax", "pretax_income", "percent"),
        _r(
            "rd_to_revenue",
            "Research and development to revenue",
            "research_and_development",
            "revenue",
            "percent",
        ),
        _r(
            "operating_cash_flow_to_revenue",
            "Operating cash flow to revenue",
            "operating_cash_flow",
            "revenue",
            "percent",
        ),
        _r("current_ratio", "Current ratio", "current_assets", "current_liabilities", "times"),
        _r(
            "liabilities_to_equity",
            "Total liabilities to stockholders' equity",
            "total_liabilities",
            "stockholders_equity",
            "times",
        ),
    )
}
