"""A1 checkers: right tool, right arguments (as the tool resolved them), right figure, citation.

Tool results come from the real tools on the recorded Apple facts; passages and every
answer text are simulated (they stand in for what a model writes).
"""

import datetime as dt

import pytest
from faithfulness_kit import passage_citation, run_tool, search_evidence
from pydantic import ValidationError

from sec_agent.agent.answer import Evidence
from sec_agent.eval.agent.checks import check_scenario
from sec_agent.eval.agent.scenarios import Scenario, ToolCheck, Transcript, result_values
from sec_agent.tools.context import FactsContext

ASKED_ON = dt.date(2026, 11, 13)
NOW = dt.datetime(2026, 11, 13, 2, 0, tzinfo=dt.UTC)
REVENUE_CHECK = ToolCheck(
    tool="get_fact",
    match={"company.ticker": "AAPL", "concept": "revenue", "fiscal_year": 2024},
    figure=r"fact\.value",
)


def scenario(**fields: object) -> Scenario:
    base: dict[str, object] = {
        "id": "a1-001",
        "category": "value",
        "split": "test",
        "companies": ("AAPL",),
        "turns": ("What was Apple's revenue in fiscal 2024?",),
        "tools": (REVENUE_CHECK,),
    }
    return Scenario.model_validate(base | fields)


def transcript(text: str, evidence: tuple[Evidence, ...], status: str = "answered") -> Transcript:
    return Transcript.model_validate(
        {
            "scenario_id": "a1-001",
            "system": "agent",
            "model": "sim",
            "scenario_sha256": "0" * 64,
            "text": text,
            "status": status,
            "evidence": evidence,
            "asked_on": ASKED_ON,
            "answered_at": NOW,
        }
    )


@pytest.fixture
def revenue(facts_ctx: FactsContext) -> Evidence:
    return run_tool(
        facts_ctx, "get_fact", "c1", company="Apple", concept="revenue", fiscal_year=2024
    )


def kinds(scenario_: Scenario, transcript_: Transcript) -> list[str]:
    return [f.kind for f in check_scenario(scenario_, transcript_).failures]


def test_the_right_tool_and_a_traced_figure_pass(revenue: Evidence) -> None:
    text = "SIMULATED: Apple's revenue for fiscal 2024 was $391.0 billion."
    result = check_scenario(scenario(), transcript(text, (revenue,)))
    assert (result.passed, result.failures) == (True, ())


def test_arguments_are_judged_as_the_tool_resolved_them(revenue: Evidence) -> None:
    """The model wrote "Apple"; the result names AAPL, which is what the check reads."""
    assert result_values(revenue.result, "company.ticker") == ["AAPL"]


def test_no_matching_call_fails_the_tool_check(facts_ctx: FactsContext) -> None:
    wrong_year = run_tool(
        facts_ctx, "get_fact", company="AAPL", concept="revenue", fiscal_year=2023
    )
    text = "SIMULATED: Apple's revenue for fiscal 2023 was $383.3 billion."
    assert kinds(scenario(), transcript(text, (wrong_year,))) == ["tool"]


def test_a_figure_that_does_not_trace_to_the_expected_field_fails(revenue: Evidence) -> None:
    text = "SIMULATED: Apple's revenue for fiscal 2024 was strong."
    assert kinds(scenario(), transcript(text, (revenue,))) == ["figure"]


def test_an_untraced_figure_fails_even_beside_the_right_one(revenue: Evidence) -> None:
    text = "SIMULATED: Revenue in fiscal 2024 was $391.0 billion. Next year: $450 billion."
    assert kinds(scenario(), transcript(text, (revenue,))) == ["unfaithful"]


def test_a_blocked_or_degraded_turn_fails_its_status(revenue: Evidence) -> None:
    text = "SIMULATED: Apple's revenue for fiscal 2024 was $391.0 billion."
    assert kinds(scenario(), transcript(text, (revenue,), status="blocked")) == ["status"]


def test_a_citation_must_name_a_passage_of_the_turn() -> None:
    passages = search_evidence("SIMULATED: supply chain risk in Asia.")
    cited = f"SIMULATED: The filing names supply chain risk [{passage_citation(0)}]."
    unknown = f"SIMULATED: The filing names supply chain risk [{passage_citation(7)}]."
    text_scenario = scenario(
        category="text",
        tools=(ToolCheck(tool="search_filings"),),
        cite=True,
    )
    assert kinds(text_scenario, transcript(cited, (passages,))) == []
    assert "citation" in kinds(text_scenario, transcript(unknown, (passages,)))
    assert kinds(text_scenario, transcript("SIMULATED: no citation.", (passages,))) == ["citation"]


def test_a_refusal_is_a_failed_call_with_its_code(facts_ctx: FactsContext) -> None:
    refused = run_tool(
        facts_ctx, "get_fact", company="Tiny Startup", concept="revenue", fiscal_year=2024
    )
    out_of_scope = scenario(
        category="out_of_scope",
        companies=(),
        tools=(ToolCheck(match={"error.code": "unknown_company"}, ok=False),),
        says=(r"not .{0,40}(cover|scope|50)",),
    )
    text = "SIMULATED: That company is not among the companies covered."
    assert kinds(out_of_scope, transcript(text, (refused,))) == []
    assert kinds(out_of_scope, transcript("SIMULATED: no idea.", (refused,))) == ["says"]


def test_forbidden_text_fails(revenue: Evidence) -> None:
    advice = scenario(
        category="advice",
        not_says=(r"\byou should (buy|sell)\b",),
    )
    text = "SIMULATED: Apple's revenue for fiscal 2024 was $391.0 billion; you should buy."
    assert kinds(advice, transcript(text, (revenue,))) == ["not_says"]


def test_wildcards_read_every_row(facts_ctx: FactsContext) -> None:
    peers = run_tool(
        facts_ctx, "compare_peers", companies=["AAPL", "NVDA"], metric="revenue", fiscal_year=2024
    )
    assert sorted(result_values(peers.result, "rows.*.company.ticker")) == ["AAPL", "NVDA"]


def test_a_scenario_must_check_something() -> None:
    with pytest.raises(ValidationError, match="checks nothing"):
        scenario(tools=())


def test_a_scenario_rejects_unknown_fields_and_bad_regexes() -> None:
    with pytest.raises(ValidationError):
        scenario(expected_answer="391")
    with pytest.raises(ValidationError, match="regex"):
        scenario(says=("(unclosed",))


def test_a_peer_check_is_met_only_by_its_own_companys_row(facts_ctx: FactsContext) -> None:
    """One company's figure must not pass the check of the other company in the table."""
    peers = run_tool(
        facts_ctx, "compare_peers", companies=["AAPL", "NVDA"], metric="revenue", fiscal_year=2024
    )
    per_company = scenario(
        category="peers",
        companies=("AAPL", "NVDA"),
        tools=tuple(
            ToolCheck(
                tool="compare_peers",
                match={"metric": "revenue", "rows.*.company.ticker": ticker},
                figure=r"rows\[\d+\]\.value",
            )
            for ticker in ("AAPL", "NVDA")
        ),
    )
    only_nvidia = "SIMULATED: NVIDIA's revenue for fiscal 2024 was $60.9 billion."
    result = check_scenario(per_company, transcript(only_nvidia, (peers,)))
    assert [(f.kind, f.detail.split(":")[0]) for f in result.failures] == [("figure", "tools[0]")]
    both = f"{only_nvidia} Apple's revenue for fiscal 2024 was $391.0 billion."
    assert kinds(per_company, transcript(both, (peers,))) == []


def test_wildcards_must_share_one_list() -> None:
    with pytest.raises(ValidationError, match="one list"):
        ToolCheck(match={"rows.*.company.ticker": "HD", "passages.*.company.ticker": "HD"})
