"""From a turn's evidence to what the web app shows: metric cards and citations.

Numeric evidence is produced by the real tools on the recorded Apple and NVIDIA facts, so
the figures are what SEC reported. Passages, risk diffs and the restated fact are simulated
(`faithfulness_kit`).
"""

import datetime as dt
import json
import re
from decimal import Decimal
from typing import Any, cast

from faithfulness_kit import (
    SIM_ACCESSION,
    SIM_PREVIOUS_ACCESSION,
    passage_citation,
    restated_evidence,
    risk_diff_evidence,
    run_tool,
    search_evidence,
)

from sec_agent.agent.answer import Evidence
from sec_agent.api.cards import FactCard, NoticeCard, PeersCard, RatioCard, RiskDiffCard
from sec_agent.api.present import present
from sec_agent.tools.context import FactsContext

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _revenue(facts: FactsContext, year: int = 2024, call_id: str = "c1") -> Evidence:
    return run_tool(facts, "get_fact", call_id, company="AAPL", concept="revenue", fiscal_year=year)


def test_a_reported_fact_becomes_a_card_with_its_period_unit_and_filing(
    facts_ctx: FactsContext,
) -> None:
    view = present([_revenue(facts_ctx)])
    (card,) = view.cards
    assert isinstance(card, FactCard)
    assert (card.call_id, card.status) == ("c1", "found")
    assert (card.company.ticker, card.company.name) == ("AAPL", "Apple Inc.")
    assert (card.concept, card.label, card.unit) == ("revenue", "Revenue", "USD")
    assert (card.fiscal_year, card.fiscal_period) == (2024, "FY")
    assert card.value == Decimal("391035000000")
    assert card.period_end == dt.date(2024, 9, 28), "E1: the fiscal year's own end date"
    assert card.source is not None
    assert card.source.form == "10-K"
    assert card.source.url.startswith("https://www.sec.gov/Archives/edgar/data/320193/")
    assert card.source.accession in card.source.url
    assert not card.restated


def test_a_value_is_sent_as_the_exact_text_the_tool_returned(facts_ctx: FactsContext) -> None:
    sent = json.loads(present([_revenue(facts_ctx)]).model_dump_json())
    assert sent["cards"][0]["value"] == "391035000000"
    assert sent["cards"][0]["period_end"] == "2024-09-28"


def test_a_restated_fact_keeps_the_latest_value_and_shows_the_original() -> None:
    """E2: the latest filed value is the figure; the first filed one is the note."""
    (card,) = present([restated_evidence()]).cards
    assert isinstance(card, FactCard)
    assert card.restated
    assert (card.value, card.original_value) == (Decimal("1250000000"), Decimal("1200000000"))
    assert card.original_filed == dt.date(2025, 2, 20)
    assert card.source is not None
    assert card.source.form == "10-K/A"


def test_a_value_that_was_not_reported_is_a_card_that_says_so(facts_ctx: FactsContext) -> None:
    """E12: no figure is shown, and none is estimated."""
    (card,) = present([_revenue(facts_ctx, 2019)]).cards
    assert isinstance(card, FactCard)
    assert (card.status, card.value, card.source) == ("not_reported", None, None)
    assert card.fiscal_year == 2019


def test_a_ratio_card_shows_the_formula_and_the_facts_it_was_computed_from(
    facts_ctx: FactsContext,
) -> None:
    evidence = run_tool(
        facts_ctx, "compute_ratio", "c2", company="AAPL", ratio="gross_margin", fiscal_year=2024
    )
    (card,) = present([evidence]).cards
    assert isinstance(card, RatioCard)
    assert (card.status, card.value, card.unit) == ("computed", Decimal("46.206350"), "percent")
    assert card.formula == "gross_profit / revenue * 100"
    assert card.period_end == dt.date(2024, 9, 28)
    assert [(i.concept, i.value) for i in card.inputs] == [
        ("gross_profit", Decimal("180683000000")),
        ("revenue", Decimal("391035000000")),
    ]
    assert all(i.source.url.startswith("https://www.sec.gov/") for i in card.inputs)


def test_a_peer_comparison_keeps_each_company_on_its_own_period_end(
    facts_ctx: FactsContext,
) -> None:
    """E3: fiscal years are not converted; the card carries each period end."""
    evidence = run_tool(
        facts_ctx,
        "compare_peers",
        "c3",
        companies=["AAPL", "NVDA"],
        metric="gross_margin",
        fiscal_year=2024,
    )
    (card,) = present([evidence]).cards
    assert isinstance(card, PeersCard)
    assert (card.label, card.unit, card.fiscal_year) == ("Gross margin", "percent", 2024)
    assert [(r.rank, r.company.ticker, r.value, r.period_end) for r in card.rows] == [
        (1, "NVDA", Decimal("72.717573"), dt.date(2024, 1, 28)),
        (2, "AAPL", Decimal("46.206350"), dt.date(2024, 9, 28)),
    ]
    assert not card.same_period_end
    assert card.note


def test_passages_become_citations_keyed_as_the_answer_cites_them() -> None:
    view = present([search_evidence("SIMULATED passage one.", "SIMULATED passage two.")])
    assert view.cards == ()
    first, second = view.citations
    assert (first.key, first.kind) == (passage_citation(0), "passage")
    assert (first.text, second.text) == ("SIMULATED passage one.", "SIMULATED passage two.")
    assert (first.form, first.section) == ("10-K", "mdna")
    assert first.company is not None
    assert first.company.ticker == "SIMW"
    assert (first.filing_date, first.report_date) == (dt.date(2025, 2, 20), dt.date(2024, 12, 31))
    assert first.url.startswith("https://www.sec.gov/Archives/")


def test_the_filing_behind_a_fact_is_a_citation_too(facts_ctx: FactsContext) -> None:
    """An answer may cite a bare accession number; the panel links it to the filing."""
    view = present([_revenue(facts_ctx), _revenue(facts_ctx, call_id="c9")])
    (citation,) = view.citations  # one filing is listed once
    (card, _) = view.cards
    assert isinstance(card, FactCard)
    assert card.source is not None
    assert (citation.key, citation.kind) == (card.source.accession, "filing")
    assert (citation.text, citation.section) == (None, None)
    assert citation.url == card.source.url


def test_a_risk_factor_diff_is_a_card_with_both_filings_and_the_changed_text() -> None:
    view = present([risk_diff_evidence("SIMULATED new risk about supply.")])
    (card,) = view.cards
    assert isinstance(card, RiskDiffCard)
    assert (card.status, card.added, card.removed, card.changed, card.unchanged) == (
        "compared",
        1,
        0,
        0,
        2,
    )
    assert card.current is not None
    assert card.previous is not None
    assert (card.current.fiscal_year, card.previous.fiscal_year) == (2024, 2023)
    assert [(c.kind, c.text) for c in card.changes] == [
        ("added", "SIMULATED new risk about supply.")
    ]
    assert [c.key for c in view.citations] == [SIM_ACCESSION, SIM_PREVIOUS_ACCESSION]


def test_a_tool_refusal_is_a_notice_not_a_figure(facts_ctx: FactsContext) -> None:
    """E7: a company outside the universe is said to be out of scope."""
    refused = run_tool(
        facts_ctx, "get_fact", "c4", company="ZZZZ", concept="revenue", fiscal_year=2024
    )
    (card,) = present([refused]).cards
    assert isinstance(card, NoticeCard)
    assert (card.call_id, card.tool, card.code) == ("c4", "get_fact", "unknown_company")
    assert "ZZZZ" in card.message


def test_evidence_that_cannot_be_read_is_left_out_without_failing() -> None:
    broken = Evidence(call_id="c5", name="get_fact", arguments="{}", result="{not json", ok=True)
    unknown = Evidence(call_id="c6", name="mystery_tool", arguments="{}", result="{}", ok=True)
    view = present([broken, unknown])
    assert (view.cards, view.citations) == ((), ())


def test_cards_and_citations_keep_the_order_of_the_evidence(facts_ctx: FactsContext) -> None:
    nvidia = run_tool(
        facts_ctx, "get_fact", "c2", company="NVDA", concept="revenue", fiscal_year=2024
    )
    view = present([_revenue(facts_ctx, 2024, "c1"), search_evidence("SIMULATED passage."), nvidia])
    assert [c.call_id for c in view.cards] == ["c1", "c2"]
    assert [c.kind for c in view.citations] == ["filing", "passage", "filing"]


def _numbers(value: Any) -> set[str]:
    """Every decimal value in a dumped view: strings that are numbers, nothing else."""
    if isinstance(value, dict):
        return {n for item in cast(dict[str, Any], value).values() for n in _numbers(item)}
    if isinstance(value, list):
        return {n for item in cast(list[Any], value) for n in _numbers(item)}
    if isinstance(value, str) and _NUMBER.fullmatch(value):
        return {value}
    return set()


def test_every_figure_shown_is_a_figure_of_the_evidence(facts_ctx: FactsContext) -> None:
    """Numbers come from tools: presenting adds, rounds and converts nothing."""
    evidence = [
        _revenue(facts_ctx),
        run_tool(
            facts_ctx, "compute_ratio", "c2", company="NVDA", ratio="net_margin", fiscal_year=2024
        ),
        run_tool(
            facts_ctx,
            "compare_peers",
            "c3",
            companies=["AAPL", "NVDA"],
            metric="revenue",
            fiscal_year=2024,
        ),
        restated_evidence(),
    ]
    shown = _numbers(json.loads(present(evidence).model_dump_json()))
    source = " ".join(e.result for e in evidence)
    assert shown, "the view holds figures"
    assert all(f'"{figure}"' in source for figure in shown), shown
