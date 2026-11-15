"""Degraded mode: the figures a question asks for, looked up without any model.

The numeric tools are the real ones on the recorded Apple and NVIDIA facts, so the values
are what SEC reported. The search result is simulated (`faithfulness_kit`). Questions are
asked on 2026-11-13: Apple's latest reported fiscal year is then 2025, NVIDIA's 2026.
"""

import json
from typing import Any

from api_kit import RecordingTools
from faithfulness_kit import ASKED_ON, search_evidence

from sec_agent.agent.answer import Evidence
from sec_agent.degraded.lookup import MAX_CALLS, deterministic_evidence
from sec_agent.tools.context import FactsContext


def _lookup(
    question: str, facts: FactsContext, *, search_result: str | None = None
) -> tuple[tuple[Evidence, ...], RecordingTools]:
    tools = RecordingTools(facts, search_result=search_result)
    evidence = deterministic_evidence(
        question, tools=tools, companies=facts.companies, asked_on=ASKED_ON
    )
    return evidence, tools


def _result(evidence: Evidence) -> Any:
    return json.loads(evidence.result)


def _arguments(evidence: Evidence) -> Any:
    return json.loads(evidence.arguments)


def test_a_fact_of_a_named_fiscal_year_is_looked_up(facts_ctx: FactsContext) -> None:
    evidence, tools = _lookup("What was Apple's revenue in fiscal 2024?", facts_ctx)
    (fact,) = evidence
    assert (fact.name, fact.ok, fact.call_id) == ("get_fact", True, "d1")
    assert _arguments(fact) == {
        "company": "AAPL",
        "concept": "revenue",
        "fiscal_year": 2024,
        "fiscal_period": "FY",
    }
    assert _result(fact)["fact"]["value"] == "391035000000"
    assert _result(fact)["fact"]["period_end"] == "2024-09-28"
    assert len(tools.calls) == 1


def test_without_a_year_the_latest_reported_fiscal_year_is_shown(
    facts_ctx: FactsContext,
) -> None:
    """E6: the period used is whatever the card states, never an assumed calendar year."""
    apple, _ = _lookup("Apple revenue", facts_ctx)
    (fact,) = apple  # the empty probe of fiscal 2026 is not shown
    assert (_result(fact)["fiscal_year"], _result(fact)["fact"]["value"]) == (
        2025,
        "416161000000",
    )
    nvidia, _ = _lookup("NVDA revenue", facts_ctx)
    assert _result(nvidia[0])["fiscal_year"] == 2026


def test_a_span_of_years_ends_at_the_latest_reported_one(facts_ctx: FactsContext) -> None:
    evidence, _ = _lookup("Apple revenue over the last 3 years", facts_ctx)
    assert [(_result(e)["fiscal_year"], _result(e)["fact"]["value"]) for e in evidence] == [
        (2023, "383285000000"),
        (2024, "391035000000"),
        (2025, "416161000000"),
    ]
    assert [e.call_id for e in evidence] == ["d1", "d2", "d3"]


def test_a_ratio_is_computed_by_the_ratio_tool(facts_ctx: FactsContext) -> None:
    evidence, _ = _lookup("Apple gross margin 2024", facts_ctx)
    (ratio,) = evidence
    assert ratio.name == "compute_ratio"
    assert (_result(ratio)["ratio"], _result(ratio)["value"]) == ("gross_margin", "46.206350")


def test_a_growth_question_adds_the_change_from_the_year_before(facts_ctx: FactsContext) -> None:
    evidence, _ = _lookup("How fast did Apple's revenue grow in 2024?", facts_ctx)
    fact, growth = evidence
    assert (fact.name, growth.name) == ("get_fact", "compute_ratio")
    assert _arguments(growth)["ratio"] == "yoy_growth"
    assert _arguments(growth)["concept"] == "revenue"
    assert _result(growth)["value"] == "2.021994"


def test_several_companies_are_compared_by_the_peer_tool(facts_ctx: FactsContext) -> None:
    evidence, _ = _lookup("NVDA vs AAPL gross margin 2024", facts_ctx)
    (peers,) = evidence
    assert peers.name == "compare_peers"
    assert _arguments(peers)["companies"] == ["NVDA", "AAPL"]
    assert [r["company"]["ticker"] for r in _result(peers)["rows"]] == ["NVDA", "AAPL"]


def test_a_question_about_peers_compares_the_company_with_its_sector(
    facts_ctx: FactsContext,
) -> None:
    evidence, _ = _lookup("How does Apple's gross margin compare to its peers in 2024?", facts_ctx)
    assert [e.name for e in evidence] == ["compute_ratio", "compare_peers"]
    assert _arguments(evidence[1])["peers_of"] == "AAPL"


def test_a_company_without_a_named_figure_gets_revenue_and_net_income(
    facts_ctx: FactsContext,
) -> None:
    evidence, _ = _lookup("Tell me about Apple in 2024", facts_ctx)
    assert [_arguments(e)["concept"] for e in evidence] == ["revenue", "net_income"]


def test_a_value_that_is_not_reported_stays_not_reported(facts_ctx: FactsContext) -> None:
    """E12: Microsoft has no facts in the recorded fixtures; nothing is estimated."""
    evidence, tools = _lookup("Microsoft revenue", facts_ctx)
    (fact,) = evidence
    assert (fact.ok, _result(fact)["status"]) == (True, "not_reported")
    assert _result(fact)["fiscal_year"] == ASKED_ON.year, "the first year probed is the one shown"
    assert len(tools.calls) <= 5, "the probe for the latest year is bounded"


def test_a_question_that_names_no_company_looks_up_no_figure(facts_ctx: FactsContext) -> None:
    evidence, tools = _lookup("Which company has the highest gross margin?", facts_ctx)
    assert evidence == ()
    assert tools.calls == []


def test_filing_text_is_searched_when_a_text_index_is_served(facts_ctx: FactsContext) -> None:
    passages = search_evidence("SIMULATED passage about supply.").result
    question = "What does Apple say about supply risks?"
    evidence, tools = _lookup(question, facts_ctx, search_result=passages)
    search = evidence[-1]
    assert (search.name, search.ok, search.result) == ("search_filings", True, passages)
    assert tools.calls[-1] == ("search_filings", {"query": question, "companies": ["AAPL"], "k": 5})


def test_a_question_without_a_company_still_searches_the_text(facts_ctx: FactsContext) -> None:
    passages = search_evidence("SIMULATED passage.").result
    evidence, tools = _lookup("What is said about tariffs?", facts_ctx, search_result=passages)
    assert [e.name for e in evidence] == ["search_filings"]
    assert tools.calls == [("search_filings", {"query": "What is said about tariffs?", "k": 5})]


def test_without_a_text_index_nothing_is_searched(facts_ctx: FactsContext) -> None:
    _, tools = _lookup("What does Apple say about supply risks?", facts_ctx)
    assert all(name != "search_filings" for name, _ in tools.calls)


def test_the_number_of_lookups_is_bounded(facts_ctx: FactsContext) -> None:
    question = (
        "AAPL, NVDA, MSFT and AMD revenue, net income and gross margin growth "
        "over the last 5 years versus peers"
    )
    evidence, tools = _lookup(question, facts_ctx)
    assert len(tools.calls) <= MAX_CALLS
    assert len(evidence) <= MAX_CALLS


def test_every_lookup_is_a_tool_call_recorded_like_the_agents(facts_ctx: FactsContext) -> None:
    evidence, tools = _lookup("Apple revenue and gross margin 2023 to 2024", facts_ctx)
    assert len({e.call_id for e in evidence}) == len(evidence)
    recorded = [(name, arguments) for name, arguments in tools.calls]
    assert [(e.name, _arguments(e)) for e in evidence] == recorded
    assert all(e.ok for e in evidence)
