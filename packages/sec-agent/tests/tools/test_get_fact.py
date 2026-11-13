"""get_fact: one XBRL value by fiscal label, with its period, unit, filing and restatement."""

import datetime as dt
from decimal import Decimal

import pytest
from pydantic import ValidationError

from sec_agent.tools.context import FactsContext
from sec_agent.tools.errors import InvalidRequestError, UnknownCompanyError, UnknownMetricError
from sec_agent.tools.get_fact import GetFactArgs, get_fact


def _get(ctx: FactsContext, **kwargs: object) -> object:
    return get_fact(ctx, GetFactArgs.model_validate(kwargs))


def test_annual_value_carries_its_period_unit_and_filing(facts_ctx: FactsContext) -> None:
    result = get_fact(facts_ctx, GetFactArgs(company="AAPL", concept="revenue", fiscal_year=2024))
    assert result.status == "found"
    assert result.company.ticker == "AAPL"
    assert result.period_kind == "annual"
    fact = result.fact
    assert fact is not None
    assert fact.value == Decimal("391035000000")
    assert fact.unit == "USD"
    assert (fact.period_start, fact.period_end) == (dt.date(2023, 10, 1), dt.date(2024, 9, 28))
    assert (fact.fiscal_year, fact.fiscal_period) == (2024, "FY")
    assert (fact.accession, fact.form, fact.filed) == (
        "0000320193-25-000079",
        "10-K",
        dt.date(2025, 10, 31),
    )
    assert fact.tag == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert fact.filing_url == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/"
        "0000320193-25-000079-index.htm"
    )
    assert result.index_version == "x-test"


def test_off_calendar_fiscal_year_reports_its_own_end_date(facts_ctx: FactsContext) -> None:
    """E1: NVIDIA's fiscal 2024 ended on 2024-01-28, not in December 2024."""
    result = get_fact(facts_ctx, GetFactArgs(company="NVDA", concept="revenue", fiscal_year=2024))
    assert result.fact is not None
    assert result.fact.value == Decimal("60922000000")
    assert (result.fact.period_start, result.fact.period_end) == (
        dt.date(2023, 1, 30),
        dt.date(2024, 1, 28),
    )


def test_restated_value_is_the_latest_and_keeps_the_original(facts_ctx: FactsContext) -> None:
    """E2: NVIDIA's FY2024 diluted EPS was 11.93, restated to 1.19 after its stock split."""
    result = get_fact(
        facts_ctx, GetFactArgs(company="nvidia", concept="eps_diluted", fiscal_year=2024)
    )
    fact = result.fact
    assert fact is not None
    assert fact.value == Decimal("1.19")
    assert fact.unit == "USD/shares"  # E5: the unit comes from XBRL
    assert fact.restated is True
    assert fact.original_value == Decimal("11.93")
    assert fact.versions >= 2
    assert fact.original_filed < fact.filed


def test_quarter_and_year_to_date_are_different_periods(facts_ctx: FactsContext) -> None:
    quarter = get_fact(
        facts_ctx,
        GetFactArgs(company="AAPL", concept="revenue", fiscal_year=2024, fiscal_period="Q2"),
    )
    ytd = get_fact(
        facts_ctx,
        GetFactArgs(
            company="AAPL",
            concept="revenue",
            fiscal_year=2024,
            fiscal_period="Q2",
            year_to_date=True,
        ),
    )
    assert quarter.period_kind == "quarter"
    assert ytd.period_kind == "ytd"
    assert quarter.fact is not None
    assert ytd.fact is not None
    assert quarter.fact.value == Decimal("90753000000")
    assert ytd.fact.value == Decimal("210328000000")
    assert ytd.fact.period_start == dt.date(2023, 10, 1)


def test_a_balance_at_year_end_is_an_instant(facts_ctx: FactsContext) -> None:
    result = get_fact(
        facts_ctx, GetFactArgs(company="AAPL", concept="total_assets", fiscal_year=2024)
    )
    assert result.period_kind == "instant"
    assert result.fact is not None
    assert result.fact.period_start is None
    assert result.fact.period_end == dt.date(2024, 9, 28)
    assert result.fact.value == Decimal("364980000000")


def test_a_fourth_quarter_balance_is_the_year_end_balance(facts_ctx: FactsContext) -> None:
    q4 = get_fact(
        facts_ctx,
        GetFactArgs(company="AAPL", concept="total_assets", fiscal_year=2024, fiscal_period="Q4"),
    )
    fy = get_fact(facts_ctx, GetFactArgs(company="AAPL", concept="total_assets", fiscal_year=2024))
    assert q4.fact == fy.fact
    assert q4.fiscal_period == "FY"


def test_year_to_date_of_a_fourth_quarter_is_the_fiscal_year(facts_ctx: FactsContext) -> None:
    result = get_fact(
        facts_ctx,
        GetFactArgs(
            company="AAPL",
            concept="revenue",
            fiscal_year=2024,
            fiscal_period="Q4",
            year_to_date=True,
        ),
    )
    assert (result.period_kind, result.fiscal_period) == ("annual", "FY")


def test_a_balance_has_no_year_to_date(facts_ctx: FactsContext) -> None:
    with pytest.raises(InvalidRequestError, match="balance"):
        _get(facts_ctx, company="AAPL", concept="total_assets", fiscal_year=2024, year_to_date=True)


@pytest.mark.parametrize(
    ("concept", "year"),
    [("revenue", 2030), ("inventory", 2024)],
)
def test_a_value_not_reported_is_an_answer_not_an_error(
    facts_ctx: FactsContext, concept: str, year: int
) -> None:
    """E12: Apple reports no fiscal 2030 and no inventory concept in these facts."""
    result = get_fact(facts_ctx, GetFactArgs(company="AAPL", concept=concept, fiscal_year=year))
    assert result.status == "not_reported"
    assert result.fact is None
    assert result.unit == "USD"


def test_a_non_gaap_or_unknown_concept_is_refused(facts_ctx: FactsContext) -> None:
    """E4: Adjusted EBITDA is not an XBRL concept; the tool never computes one."""
    with pytest.raises(UnknownMetricError, match="non-GAAP"):
        _get(facts_ctx, company="AAPL", concept="adjusted_ebitda", fiscal_year=2024)


def test_a_company_out_of_scope_is_refused(facts_ctx: FactsContext) -> None:
    with pytest.raises(UnknownCompanyError):
        _get(facts_ctx, company="ZZZZ", concept="revenue", fiscal_year=2024)


@pytest.mark.parametrize(
    "bad",
    [
        {"fiscal_year": 1899},
        {"fiscal_year": 2024, "fiscal_period": "Q5"},
        {"fiscal_year": 2024, "extra": 1},
    ],
)
def test_arguments_are_validated(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GetFactArgs.model_validate({"company": "AAPL", "concept": "revenue", **bad})
