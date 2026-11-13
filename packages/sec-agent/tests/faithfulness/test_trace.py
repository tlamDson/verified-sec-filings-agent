"""Tracing each figure, date and citation of an answer to the evidence of its turn.

Tool evidence comes from the real tools on the recorded Apple and NVIDIA facts; passages
and risk diffs are simulated. Every answer sentence is simulated model text.
"""

from collections.abc import Sequence

import pytest
from faithfulness_kit import (
    ASKED_ON,
    SIM_ACCESSION,
    passage_citation,
    restated_evidence,
    risk_diff_evidence,
    run_tool,
    search_evidence,
)

from sec_agent.agent.answer import Evidence
from sec_agent.faithfulness.check import check_answer
from sec_agent.faithfulness.models import FaithfulnessReport, MentionCheck
from sec_agent.tools.context import FactsContext


def _checks(text: str, evidence: Sequence[Evidence]) -> list[MentionCheck]:
    report = check_answer(text, evidence, asked_on=ASKED_ON)
    return [m for s in report.sentences for m in s.mentions]


def _statuses(text: str, evidence: Sequence[Evidence]) -> list[str]:
    return [m.status for m in _checks(text, evidence)]


@pytest.fixture
def revenue(facts_ctx: FactsContext) -> Evidence:
    return run_tool(
        facts_ctx, "get_fact", "c1", company="AAPL", concept="revenue", fiscal_year=2024
    )


def test_a_figure_from_a_tool_result_is_traced_to_its_call_and_field(revenue: Evidence) -> None:
    (check,) = _checks("Apple's revenue for fiscal 2024 was $391.0 billion.", [revenue])
    assert check.status == "traced"
    assert check.source is not None
    assert (check.source.call_id, check.source.tool, check.source.field) == (
        "c1",
        "get_fact",
        "fact.value",
    )


@pytest.mark.parametrize(
    ("figure", "status"),
    [
        ("$391 billion", "traced"),
        ("$391.0 billion", "traced"),
        ("$391.04 billion", "traced"),
        ("$391,035 million", "traced"),
        ("$391,035,000,000", "traced"),
        ("$390 billion", "untraced"),
        ("$391.1 billion", "untraced"),
        ("about $400 billion", "untraced"),
        ("$391.035 million", "untraced"),
    ],
)
def test_a_figure_matches_only_when_rounding_the_tool_value_gives_it(
    revenue: Evidence, figure: str, status: str
) -> None:
    """391,035,000,000 shown with fewer digits is fine; a different value or scale is not."""
    assert _statuses(f"Apple's fiscal 2024 revenue was {figure}.", [revenue]) == [status]


def test_a_figure_in_the_wrong_unit_is_rejected(facts_ctx: FactsContext) -> None:
    """E5: the value is right but the unit is not the one XBRL reports."""
    eps = run_tool(facts_ctx, "get_fact", company="AAPL", concept="eps_diluted", fiscal_year=2024)
    margin = run_tool(
        facts_ctx, "compute_ratio", "c2", company="AAPL", ratio="gross_margin", fiscal_year=2024
    )
    assert _statuses("Apple's diluted EPS for fiscal 2024 was 6.08%.", [eps]) == ["wrong_unit"]
    assert _statuses("Its gross margin was $46.21.", [margin]) == ["wrong_unit"]
    assert _statuses("Its gross margin was 46.21 times.", [margin]) == ["wrong_unit"]
    assert _statuses("Diluted EPS was $6.08 per share.", [eps]) == ["traced"]
    assert _statuses("Its gross margin was 46.2%.", [margin]) == ["traced"]


def test_a_figure_for_another_period_than_the_sentence_names_is_rejected(
    revenue: Evidence,
) -> None:
    """E1: fiscal 2024's revenue stated as fiscal 2023's."""
    assert _statuses("Apple's revenue for fiscal 2023 was $391.0 billion.", [revenue]) == [
        "wrong_period"
    ]
    assert _statuses("Apple's revenue was $391.0 billion.", [revenue]) == ["traced"]


def test_a_fiscal_year_that_ends_early_in_the_calendar_is_read_on_its_own_dates(
    facts_ctx: FactsContext,
) -> None:
    """E1: NVIDIA's fiscal 2024 ended in January 2024, so it is not calendar 2023."""
    nvda = run_tool(facts_ctx, "get_fact", company="NVDA", concept="revenue", fiscal_year=2024)
    assert _statuses(
        "NVIDIA's revenue for fiscal 2024, which ended January 28, 2024, was $60.9 billion.",
        [nvda],
    ) == ["traced", "traced"]
    assert _statuses("NVIDIA's revenue in calendar 2023 was $60.9 billion.", [nvda]) == [
        "wrong_period"
    ]


def test_a_number_the_model_computed_itself_is_untraced(facts_ctx: FactsContext) -> None:
    peers = run_tool(
        facts_ctx, "compare_peers", companies=["AAPL", "NVDA"], metric="revenue", fiscal_year=2024
    )
    text = "Apple's revenue of $391.0 billion exceeded NVIDIA's $60.9 billion by $330.1 billion."
    assert _statuses(text, [peers]) == ["traced", "traced", "untraced"]


def test_ranks_and_the_inputs_of_a_ratio_are_figures_of_the_result(
    facts_ctx: FactsContext,
) -> None:
    peers = run_tool(
        facts_ctx, "compare_peers", companies=["AAPL", "NVDA"], metric="revenue", fiscal_year=2024
    )
    growth = run_tool(
        facts_ctx,
        "compute_ratio",
        "c2",
        company="AAPL",
        ratio="yoy_growth",
        concept="revenue",
        fiscal_year=2024,
    )
    assert _statuses("Apple ranked 1st and NVIDIA 2nd.", [peers]) == ["traced", "traced"]
    assert _statuses("Apple ranked 3rd.", [peers]) == ["untraced"]
    text = "Revenue grew 2.0% from $383.3 billion in fiscal 2023 to $391.0 billion in fiscal 2024."
    assert _statuses(text, [growth]) == ["traced", "traced", "traced"]


def test_a_restated_value_and_the_value_first_reported_are_both_traced() -> None:
    """E2: the latest filed value, with a note that the original differed."""
    text = (
        "SIM Widgets' fiscal 2024 revenue was $1.25 billion, restated from the "
        "$1.2 billion first reported."
    )
    checks = _checks(text, [restated_evidence()])
    assert [c.status for c in checks] == ["traced", "traced"]
    assert [c.source.field for c in checks if c.source] == ["fact.value", "fact.original_value"]


def test_a_figure_from_filing_text_needs_a_citation_of_its_passage() -> None:
    passages = search_evidence(
        "SIM Widgets expects capital expenditures of $450 million in 2025.",
        "SIM Widgets sells widgets.",
    )
    cited = f"It expects capital expenditures of $450 million [{passage_citation(0)}]."
    wrong = f"It expects capital expenditures of $450 million [{passage_citation(1)}]."
    bare = "It expects capital expenditures of $450 million."
    (check,) = _checks(cited, [passages])
    assert check.status == "traced"
    assert check.source is not None
    assert (check.source.tool, check.source.citation) == ("search_filings", passage_citation(0))
    assert _statuses(wrong, [passages]) == ["uncited"]
    assert _statuses(bare, [passages]) == ["uncited"]


def test_a_passage_figure_in_a_table_stated_in_millions_matches_its_digits() -> None:
    passages = search_evidence("Net sales (in millions) 12,345 11,980")
    text = f"Net sales were $12,345 million [{passage_citation(0)}]."
    assert _statuses(text, [passages]) == ["traced"]


def test_a_citation_must_name_a_passage_or_filing_of_the_turn(revenue: Evidence) -> None:
    passages = search_evidence("SIM Widgets sells widgets.")
    report = check_answer(
        f"It sells widgets [{passage_citation(0)}]. It is old [{SIM_ACCESSION}/mdna/7]. "
        "Its 10-K says so [0000320193-25-000079].",
        [passages, revenue],
        asked_on=ASKED_ON,
    )
    statuses = [c.status for s in report.sentences for c in s.citations]
    assert statuses == ["valid", "unknown", "valid"]
    assert [s.passed for s in report.sentences] == [True, False, True]


def test_figures_of_a_risk_factor_diff_are_its_counts_and_its_cited_paragraphs() -> None:
    diff = risk_diff_evidence("SIM: a 25% tariff on imported widgets could raise costs.")
    counts = f"One risk factor was added and 2 were unchanged [{SIM_ACCESSION}]."
    paragraph = f"The new risk factor describes a 25% tariff [{SIM_ACCESSION}]."
    assert _statuses(counts, [diff]) == ["traced"]
    assert _statuses(paragraph, [diff]) == ["traced"]
    assert _statuses("The new risk factor describes a 25% tariff.", [diff]) == ["uncited"]


def test_a_date_must_be_a_date_of_the_evidence_or_the_day_asked(revenue: Evidence) -> None:
    assert _statuses("The fiscal year ended September 28, 2024.", [revenue]) == ["traced"]
    assert _statuses("The fiscal year ended September 30, 2024.", [revenue]) == ["untraced"]
    assert _statuses("As of November 13, 2026, it was the latest filing.", [revenue]) == ["traced"]


def test_a_refusal_or_an_unreadable_result_is_no_source() -> None:
    refused = Evidence(
        call_id="c1",
        name="get_fact",
        arguments="{}",
        result='{"error": {"code": "too_many_calls", "message": "at most 3 tool calls"}}',
        ok=False,
    )
    garbled = Evidence(call_id="c2", name="get_fact", arguments="{}", result="{3", ok=True)
    assert _statuses("I can make at most 3 tool calls.", [refused, garbled]) == ["untraced"]


def test_an_answer_saying_a_value_was_not_reported_has_nothing_to_trace(
    facts_ctx: FactsContext,
) -> None:
    """E12: "not reported" is a right answer and holds no figure."""
    missing = run_tool(
        facts_ctx, "get_fact", company="AAPL", concept="shares_outstanding", fiscal_year=2024
    )
    report: FaithfulnessReport = check_answer(
        "Apple did not report shares outstanding for fiscal 2024 in XBRL.",
        [missing],
        asked_on=ASKED_ON,
    )
    assert (report.verdict, report.mentions, report.traced, report.faithful) == (
        "pass",
        0,
        0,
        True,
    )
