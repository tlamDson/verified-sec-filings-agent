"""compare_peers: one metric for several companies, each on its own fiscal year (E3)."""

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal

import pytest
from pydantic import ValidationError

from sec_agent.tools.context import FactsContext
from sec_agent.tools.errors import InvalidRequestError, UnknownMetricError
from sec_agent.tools.fact_query import MemoryFactQuery
from sec_agent.tools.peers import ComparePeersArgs, compare_peers
from sec_agent.tools.ratio_defs import GROWTH
from sec_agent.xbrl.models import Fact
from sec_agent.xbrl.versions import LatestFact


def test_concept_ranks_companies_on_their_own_fiscal_years(facts_ctx: FactsContext) -> None:
    result = compare_peers(
        facts_ctx, ComparePeersArgs(companies=("NVDA", "AAPL"), metric="revenue", fiscal_year=2024)
    )
    assert result.metric_kind == "concept"
    assert result.unit == "USD"
    assert [(r.rank, r.company.ticker, r.value) for r in result.rows] == [
        (1, "AAPL", Decimal("391035000000")),
        (2, "NVDA", Decimal("60922000000")),
    ]
    assert [r.period_end for r in result.rows] == [dt.date(2024, 9, 28), dt.date(2024, 1, 28)]
    assert result.same_period_end is False
    assert "own fiscal year" in result.note
    assert all(len(r.inputs) == 1 for r in result.rows)


def test_ratio_metric_ranks_by_the_computed_ratio(facts_ctx: FactsContext) -> None:
    result = compare_peers(
        facts_ctx,
        ComparePeersArgs(companies=("AAPL", "NVDA"), metric="gross_margin", fiscal_year=2024),
    )
    assert result.metric_kind == "ratio"
    assert result.unit == "percent"
    assert [r.company.ticker for r in result.rows] == ["NVDA", "AAPL"]
    assert result.rows[1].value == Decimal("46.206350")
    assert all(len(r.inputs) == 2 for r in result.rows)


def test_a_company_without_the_value_is_listed_unranked(facts_ctx: FactsContext) -> None:
    """E12: Microsoft's facts are not loaded here, so it has no value, and says so."""
    result = compare_peers(
        facts_ctx,
        ComparePeersArgs(companies=("MSFT", "AAPL", "NVDA"), metric="revenue", fiscal_year=2024),
    )
    assert [(r.rank, r.company.ticker, r.status) for r in result.rows] == [
        (1, "AAPL", "found"),
        (2, "NVDA", "found"),
        (None, "MSFT", "not_reported"),
    ]


def test_peers_of_a_company_are_its_sector(facts_ctx: FactsContext) -> None:
    result = compare_peers(
        facts_ctx, ComparePeersArgs(peers_of="NVDA", metric="revenue", fiscal_year=2024)
    )
    tickers = {r.company.ticker for r in result.rows}
    assert {"AAPL", "NVDA", "MSFT"} <= tickers
    assert {r.company.sector for r in result.rows} == {"Information Technology"}


def test_peer_query_reads_facts_once(facts_ctx: FactsContext) -> None:
    calls: list[tuple[int, ...]] = []
    inner = facts_ctx.facts

    class Counting:
        def lookup(
            self,
            *,
            index_version: str,
            ciks: Sequence[int],
            concepts: Sequence[str],
            fiscal_years: Sequence[int],
        ) -> list[LatestFact]:
            calls.append(tuple(ciks))
            return inner.lookup(
                index_version=index_version,
                ciks=ciks,
                concepts=concepts,
                fiscal_years=fiscal_years,
            )

    ctx = FactsContext(
        companies=facts_ctx.companies, facts=Counting(), index_version=facts_ctx.index_version
    )
    args = ComparePeersArgs(companies=("AAPL", "NVDA"), metric="revenue", fiscal_year=2024)
    compare_peers(ctx, args)
    assert len(calls) == 1
    assert set(calls[0]) == {320193, 1045810}


def _sim_revenue(cik: int, value: int) -> Fact:
    return Fact(
        cik=cik,
        concept="revenue",
        unit="USD",
        period_kind="annual",
        period_start=dt.date(2099, 1, 1),
        period_end=dt.date(2099, 12, 31),
        fiscal_year=2099,
        fiscal_period="FY",
        value=Decimal(value),
        taxonomy="us-gaap",
        tag="Revenues",
        accession=f"{cik:010d}-99-000001",
        form="10-K",
        filed=dt.date(2100, 2, 1),
    )


def test_equal_values_share_a_rank(facts_ctx: FactsContext) -> None:
    """Simulated facts: two companies tie, the third ranks after both."""
    query = MemoryFactQuery.from_facts(
        "x-sim",
        [_sim_revenue(320193, 5), _sim_revenue(1045810, 5), _sim_revenue(789019, 3)],
    )
    ctx = FactsContext(companies=facts_ctx.companies, facts=query, index_version="x-sim")
    args = ComparePeersArgs(companies=("MSFT", "NVDA", "AAPL"), metric="revenue", fiscal_year=2099)
    result = compare_peers(ctx, args)
    assert [(r.rank, r.company.ticker) for r in result.rows] == [
        (1, "AAPL"),
        (1, "NVDA"),
        (3, "MSFT"),
    ]
    assert result.same_period_end is True


def test_a_company_named_twice_is_refused(facts_ctx: FactsContext) -> None:
    args = ComparePeersArgs(companies=("AAPL", "320193"), metric="revenue", fiscal_year=2024)
    with pytest.raises(InvalidRequestError, match="twice"):
        compare_peers(facts_ctx, args)


def test_growth_is_not_a_peer_metric(facts_ctx: FactsContext) -> None:
    args = ComparePeersArgs(companies=("AAPL", "NVDA"), metric=GROWTH, fiscal_year=2024)
    with pytest.raises(InvalidRequestError):
        compare_peers(facts_ctx, args)


def test_unknown_metric_is_refused(facts_ctx: FactsContext) -> None:
    args = ComparePeersArgs(companies=("AAPL", "NVDA"), metric="adjusted_ebitda", fiscal_year=2024)
    with pytest.raises(UnknownMetricError):
        compare_peers(facts_ctx, args)


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"companies": ("AAPL",)},
        {"companies": ("AAPL", "NVDA"), "peers_of": "AAPL"},
        {"companies": tuple(f"T{i}" for i in range(11))},
    ],
)
def test_exactly_one_company_list_of_two_to_ten(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ComparePeersArgs.model_validate({"metric": "revenue", "fiscal_year": 2024, **bad})
