"""Chart series built from the cards of a turn. The figures are the recorded Apple and
NVIDIA facts; a chart point is always the value of one card, never a new number."""

import datetime as dt
from decimal import Decimal

from faithfulness_kit import run_tool

from sec_agent.agent.answer import Evidence
from sec_agent.api.cards import Card
from sec_agent.api.charts import charts_of
from sec_agent.api.present import present
from sec_agent.tools.context import FactsContext


def _fact(facts: FactsContext, company: str, concept: str, year: int) -> Evidence:
    return run_tool(
        facts,
        "get_fact",
        f"{company}-{concept}-{year}",
        company=company,
        concept=concept,
        fiscal_year=year,
    )


def _ratio(facts: FactsContext, company: str, ratio: str, year: int) -> Evidence:
    return run_tool(
        facts,
        "compute_ratio",
        f"{company}-{ratio}-{year}",
        company=company,
        ratio=ratio,
        fiscal_year=year,
    )


def _cards(*evidence: Evidence) -> tuple[Card, ...]:
    return present(evidence).cards


def test_one_concept_over_several_fiscal_years_is_a_trend_in_year_order(
    facts_ctx: FactsContext,
) -> None:
    cards = _cards(*(_fact(facts_ctx, "AAPL", "revenue", year) for year in (2024, 2022, 2023)))
    (chart,) = charts_of(cards)
    assert (chart.kind, chart.title, chart.unit) == ("trend", "Revenue", "USD")
    (series,) = chart.series
    assert series.name == "AAPL"
    assert [(p.x, p.value, p.period_end) for p in series.points] == [
        ("FY2022", Decimal("394328000000"), dt.date(2022, 9, 24)),
        ("FY2023", Decimal("383285000000"), dt.date(2023, 9, 30)),
        ("FY2024", Decimal("391035000000"), dt.date(2024, 9, 28)),
    ]


def test_one_value_alone_is_not_a_chart(facts_ctx: FactsContext) -> None:
    assert charts_of(_cards(_fact(facts_ctx, "AAPL", "revenue", 2024))) == ()


def test_two_companies_share_a_chart_and_keep_their_own_period_ends(
    facts_ctx: FactsContext,
) -> None:
    """E3: the x axis is each company's fiscal year; period ends are not aligned."""
    cards = _cards(
        *(_ratio(facts_ctx, "NVDA", "gross_margin", year) for year in (2023, 2024)),
        *(_ratio(facts_ctx, "AAPL", "gross_margin", year) for year in (2023, 2024)),
    )
    (chart,) = charts_of(cards)
    assert (chart.kind, chart.title, chart.unit) == ("trend", "Gross margin", "percent")
    nvda, aapl = chart.series
    assert (nvda.name, aapl.name) == ("NVDA", "AAPL")
    assert [p.x for p in nvda.points] == ["FY2023", "FY2024"]
    assert nvda.points[1].period_end == dt.date(2024, 1, 28)
    assert aapl.points[1].period_end == dt.date(2024, 9, 28)
    assert aapl.points[1].value == Decimal("46.206350")


def test_different_metrics_are_never_drawn_on_one_axis(facts_ctx: FactsContext) -> None:
    cards = _cards(
        *(_fact(facts_ctx, "AAPL", "revenue", year) for year in (2023, 2024)),
        *(_fact(facts_ctx, "AAPL", "net_income", year) for year in (2023, 2024)),
        *(_ratio(facts_ctx, "AAPL", "net_margin", year) for year in (2023, 2024)),
    )
    assert [(c.title, c.unit) for c in charts_of(cards)] == [
        ("Revenue", "USD"),
        ("Net income", "USD"),
        ("Net margin", "percent"),
    ]


def test_a_value_that_was_not_reported_is_left_out_of_the_series(
    facts_ctx: FactsContext,
) -> None:
    """E12: a gap stays a gap; nothing is interpolated."""
    cards = _cards(*(_fact(facts_ctx, "AAPL", "revenue", year) for year in (2019, 2023, 2024)))
    (chart,) = charts_of(cards)
    assert [p.x for p in chart.series[0].points] == ["FY2023", "FY2024"]


def test_the_same_value_asked_twice_is_plotted_once(facts_ctx: FactsContext) -> None:
    cards = _cards(
        _fact(facts_ctx, "AAPL", "revenue", 2023),
        _fact(facts_ctx, "AAPL", "revenue", 2024),
        _fact(facts_ctx, "AAPL", "revenue", 2024),
    )
    (chart,) = charts_of(cards)
    assert [p.x for p in chart.series[0].points] == ["FY2023", "FY2024"]


def test_a_peer_comparison_is_a_bar_per_company_in_rank_order(facts_ctx: FactsContext) -> None:
    evidence = run_tool(
        facts_ctx,
        "compare_peers",
        "p1",
        companies=["AAPL", "NVDA"],
        metric="gross_margin",
        fiscal_year=2024,
    )
    (chart,) = charts_of(_cards(evidence))
    assert (chart.kind, chart.title, chart.unit) == ("peers", "Gross margin, FY2024", "percent")
    (series,) = chart.series
    assert [(p.x, p.value, p.period_end) for p in series.points] == [
        ("NVDA", Decimal("72.717573"), dt.date(2024, 1, 28)),
        ("AAPL", Decimal("46.206350"), dt.date(2024, 9, 28)),
    ]


def test_a_comparison_with_fewer_than_two_values_is_not_a_chart(facts_ctx: FactsContext) -> None:
    evidence = run_tool(
        facts_ctx,
        "compare_peers",
        "p1",
        companies=["AAPL", "MSFT"],
        metric="revenue",
        fiscal_year=2024,
    )
    assert charts_of(_cards(evidence)) == ()
