"""compute_ratio: ratios and year-over-year growth in code, from facts of one exact period."""

import datetime as dt
from decimal import Decimal

import pytest

from sec_agent.tools.context import FactsContext
from sec_agent.tools.errors import InvalidRequestError, UnknownMetricError
from sec_agent.tools.fact_query import MemoryFactQuery
from sec_agent.tools.ratio_defs import GROWTH, RATIOS
from sec_agent.tools.ratios import ComputeRatioArgs, RatioResult, compute_ratio
from sec_agent.xbrl.concepts import concept
from sec_agent.xbrl.models import Fact

PLACES = Decimal("0.000001")


def _ratio(ctx: FactsContext, **kwargs: object) -> RatioResult:
    return compute_ratio(ctx, ComputeRatioArgs.model_validate(kwargs))


def test_ratio_parts_share_a_period_type() -> None:
    for ratio in RATIOS.values():
        num, den = concept(ratio.numerator), concept(ratio.denominator)
        assert num.period_type == den.period_type, ratio.name
        assert num.unit == den.unit, ratio.name


def test_gross_margin_is_computed_from_the_two_facts(facts_ctx: FactsContext) -> None:
    result = _ratio(facts_ctx, company="AAPL", ratio="gross_margin", fiscal_year=2024)
    assert result.status == "computed"
    assert result.unit == "percent"
    expected = (Decimal("180683000000") / Decimal("391035000000") * 100).quantize(PLACES)
    assert result.value == expected
    assert result.value == Decimal("46.206350")
    assert [f.concept for f in result.inputs] == ["gross_profit", "revenue"]
    assert result.period_end == dt.date(2024, 9, 28)
    assert result.formula == "gross_profit / revenue * 100"


def test_off_calendar_ratio_uses_the_fiscal_year(facts_ctx: FactsContext) -> None:
    result = _ratio(facts_ctx, company="NVDA", ratio="gross_margin", fiscal_year=2024)
    assert result.value == (Decimal(44301) / Decimal(60922) * 100).quantize(PLACES)
    assert result.period_end == dt.date(2024, 1, 28)


def test_balance_ratio_in_times(facts_ctx: FactsContext) -> None:
    result = _ratio(facts_ctx, company="AAPL", ratio="current_ratio", fiscal_year=2024)
    assert result.unit == "times"
    assert result.period_kind == "instant"
    assert result.value == (Decimal(152987) / Decimal(176392)).quantize(PLACES)


def test_negative_tax_expense_over_positive_income_is_computed(facts_ctx: FactsContext) -> None:
    result = _ratio(facts_ctx, company="NVDA", ratio="effective_tax_rate", fiscal_year=2023)
    assert result.status == "computed"
    assert result.value == (Decimal(-187) / Decimal(4181) * 100).quantize(PLACES)


def test_year_over_year_growth(facts_ctx: FactsContext) -> None:
    result = _ratio(facts_ctx, company="AAPL", ratio=GROWTH, concept="revenue", fiscal_year=2024)
    assert result.status == "computed"
    assert result.unit == "percent"
    expected = ((Decimal(391035) - Decimal(383285)) / abs(Decimal(383285)) * 100).quantize(PLACES)
    assert result.value == expected
    assert [(f.fiscal_year, f.value) for f in result.inputs] == [
        (2023, Decimal("383285000000")),
        (2024, Decimal("391035000000")),
    ]
    assert result.formula == "(revenue[2024] - revenue[2023]) / |revenue[2023]| * 100"


def test_quarterly_growth_compares_the_same_fiscal_quarter(facts_ctx: FactsContext) -> None:
    result = _ratio(
        facts_ctx,
        company="AAPL",
        ratio=GROWTH,
        concept="revenue",
        fiscal_year=2024,
        fiscal_period="Q2",
    )
    assert [(f.fiscal_year, f.fiscal_period, f.period_kind) for f in result.inputs] == [
        (2023, "Q2", "quarter"),
        (2024, "Q2", "quarter"),
    ]
    expected = ((Decimal(90753) - Decimal(94836)) / Decimal(94836) * 100).quantize(PLACES)
    assert result.value == expected


def test_growth_needs_a_concept(facts_ctx: FactsContext) -> None:
    with pytest.raises(InvalidRequestError, match="concept"):
        _ratio(facts_ctx, company="AAPL", ratio=GROWTH, fiscal_year=2024)


def test_a_ratio_with_a_missing_part_is_not_reported(facts_ctx: FactsContext) -> None:
    """E12: no fiscal 2030 facts, so no ratio; the reason names what is missing."""
    result = _ratio(facts_ctx, company="AAPL", ratio="gross_margin", fiscal_year=2030)
    assert result.status == "not_reported"
    assert result.value is None
    assert result.reason is not None
    assert "gross_profit" in result.reason


def test_growth_without_the_prior_year_is_not_reported(facts_ctx: FactsContext) -> None:
    result = _ratio(facts_ctx, company="AAPL", ratio=GROWTH, concept="revenue", fiscal_year=2012)
    assert result.status == "not_reported"


def _sim_fact(concept_name: str, value: str, *, start: dt.date | None = None) -> Fact:
    return Fact(
        cik=320193,
        concept=concept_name,
        unit="USD",
        period_kind="annual" if start else "instant",
        period_start=start,
        period_end=dt.date(2099, 12, 31),
        fiscal_year=2099,
        fiscal_period="FY",
        value=Decimal(value),
        taxonomy="us-gaap",
        tag="Simulated",
        accession="9999999999-99-000001",
        form="10-K",
        filed=dt.date(2100, 2, 1),
    )


def _sim_ctx(facts_ctx: FactsContext, *facts: Fact) -> FactsContext:
    """Simulated facts for edge cases the recorded fixtures do not show."""
    query = MemoryFactQuery.from_facts(facts_ctx.index_version, facts)
    return FactsContext(
        companies=facts_ctx.companies, facts=query, index_version=facts_ctx.index_version
    )


def test_a_non_positive_denominator_is_undefined(facts_ctx: FactsContext) -> None:
    start = dt.date(2099, 1, 1)
    ctx = _sim_ctx(
        facts_ctx,
        _sim_fact("income_tax", "10", start=start),
        _sim_fact("pretax_income", "-50", start=start),
    )
    result = _ratio(ctx, company="AAPL", ratio="effective_tax_rate", fiscal_year=2099)
    assert result.status == "undefined"
    assert result.value is None
    assert result.reason is not None
    assert "not positive" in result.reason
    assert len(result.inputs) == 2


def test_parts_of_different_periods_are_never_combined(facts_ctx: FactsContext) -> None:
    ctx = _sim_ctx(
        facts_ctx,
        _sim_fact("gross_profit", "10", start=dt.date(2099, 1, 1)),
        _sim_fact("revenue", "50", start=dt.date(2099, 1, 3)),
    )
    result = _ratio(ctx, company="AAPL", ratio="gross_margin", fiscal_year=2099)
    assert result.status == "undefined"
    assert result.reason is not None
    assert "period" in result.reason


def test_unknown_ratio_is_refused(facts_ctx: FactsContext) -> None:
    with pytest.raises(UnknownMetricError, match="ebitda_margin"):
        _ratio(facts_ctx, company="AAPL", ratio="ebitda_margin", fiscal_year=2024)
