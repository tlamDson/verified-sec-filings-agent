"""A1 runs: the agent and the RAG-only baseline over scenarios, cached, then scored.

Every model reply is simulated (scripted); tool results come from the recorded Apple
facts, passages are simulated (`faithfulness_kit.search_evidence`).
"""

import datetime as dt
from collections.abc import Sequence
from pathlib import Path

import pytest
from agent_kit import agent_of
from faithfulness_kit import passage_citation, search_evidence
from llm_fakes import ScriptedProvider, call, calls, says

from sec_agent.agent.answer import Evidence
from sec_agent.eval.agent.report import agent_report
from sec_agent.eval.agent.rows import agent_rows
from sec_agent.eval.agent.runner import run_scenarios
from sec_agent.eval.agent.scenarios import Scenario, ToolCheck, Transcript
from sec_agent.eval.agent.systems import AgentScenarios, RagScenarios
from sec_agent.eval.numeric.agent_model import AgentUnavailableError
from sec_agent.eval.numeric.baselines import Message
from sec_agent.eval.numeric.runner import cache_path
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.llm.errors import ProviderUnavailableError
from sec_agent.tools.context import FactsContext

ASKED_ON = dt.date(2026, 11, 13)
NOW = dt.datetime(2026, 11, 13, 3, 0, tzinfo=dt.UTC)
REVENUE = call("get_fact", "c1", company="AAPL", concept="revenue", fiscal_year=2024)
TRACED = "SIMULATED: Apple's revenue for fiscal 2024 was $391.0 billion."
VALUE = Scenario.model_validate(
    {
        "id": "a1-001",
        "category": "value",
        "split": "test",
        "companies": ("AAPL",),
        "turns": ("What was Apple's revenue in fiscal 2024?",),
        "tools": (
            ToolCheck(
                tool="get_fact",
                match={"company.ticker": "AAPL", "fiscal_year": 2024},
                figure=r"fact\.value",
            ),
        ),
    }
)
FOLLOW_UP = VALUE.model_copy(
    update={"id": "a1-002", "turns": ("Tell me about Apple.", "And its fiscal 2024 revenue?")}
)
TEXT = Scenario.model_validate(
    {
        "id": "a1-003",
        "category": "text",
        "split": "test",
        "companies": ("AAPL",),
        "turns": ("What supply chain risks does Apple name?",),
        "tools": ({"tool": "search_filings"},),
        "cite": True,
    }
)


class ScriptedChat:
    """A stand-in chat model for the RAG baseline (simulated replies)."""

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)
        self.prompts: list[list[Message]] = []

    @property
    def name(self) -> str:
        return "sim-chat"

    def complete(self, messages: Sequence[Message]) -> str:
        self.prompts.append(list(messages))
        return self._replies.pop(0)


class FakeSearch:
    def __init__(self) -> None:
        self.asked: list[tuple[str, tuple[str, ...]]] = []

    def __call__(self, query: str, companies: tuple[str, ...]) -> Evidence:
        self.asked.append((query, companies))
        return search_evidence("SIMULATED: Apple relies on suppliers in Asia.", call_id="rag-1")


def test_the_agent_plays_every_turn_in_one_conversation_and_keeps_the_last(
    facts_ctx: FactsContext, tmp_path: Path
) -> None:
    provider = ScriptedProvider(
        "a", [says("SIMULATED: Apple makes phones."), calls(REVENUE), says(TRACED)]
    )
    system = AgentScenarios(
        agent_of(facts_ctx, provider),
        model="agent:sim",
        asked_on=ASKED_ON,
        fingerprint="sim-agent-1",
    )
    results = tmp_path / "agent.jsonl"
    summary = run_scenarios([FOLLOW_UP], system, results=results, now=lambda: NOW)
    assert (summary.asked, summary.cached) == (1, 0)
    [record] = read_jsonl(results, Transcript)
    assert (record.scenario_id, record.system, record.text, record.status) == (
        "a1-002",
        "agent",
        TRACED,
        "answered",
    )
    assert [e.call_id for e in record.evidence] == ["c1"]
    assert [m["role"] for m in provider.requests[1].messages][:3] == ["system", "user", "assistant"]


def test_a_rerun_asks_nothing_and_a_changed_scenario_asks_again(
    facts_ctx: FactsContext, tmp_path: Path
) -> None:
    provider = ScriptedProvider("a", [calls(REVENUE), says(TRACED)])
    system = AgentScenarios(
        agent_of(facts_ctx, provider),
        model="agent:sim",
        asked_on=ASKED_ON,
        fingerprint="sim-agent-1",
    )
    results = tmp_path / "agent.jsonl"
    run_scenarios([VALUE], system, results=results, now=lambda: NOW)
    again = run_scenarios([VALUE], system, results=results, now=lambda: NOW)
    assert (again.asked, again.cached) == (0, 1)
    provider.then(calls(REVENUE), says(TRACED))
    changed = VALUE.model_copy(update={"turns": ("Apple revenue, fiscal 2024?",)})
    assert run_scenarios([changed], system, results=results, now=lambda: NOW).asked == 1
    assert len(read_jsonl(cache_path(results), Transcript)) == 2
    assert len(read_jsonl(results, Transcript)) == 1


def test_no_provider_stops_the_run(facts_ctx: FactsContext, tmp_path: Path) -> None:
    provider = ScriptedProvider("a", [ProviderUnavailableError("503")])
    system = AgentScenarios(
        agent_of(facts_ctx, provider),
        model="agent:sim",
        asked_on=ASKED_ON,
        fingerprint="sim-agent-1",
    )
    with pytest.raises(AgentUnavailableError):
        run_scenarios([VALUE], system, results=tmp_path / "agent.jsonl", now=lambda: NOW)


def test_rag_answers_from_one_search_of_the_scenarios_companies(tmp_path: Path) -> None:
    search = FakeSearch()
    chat = ScriptedChat(f"SIMULATED: Apple relies on Asian suppliers [{passage_citation(0)}].")
    system = RagScenarios(search, chat, asked_on=ASKED_ON)
    results = tmp_path / "rag.jsonl"
    run_scenarios([TEXT], system, results=results, now=lambda: NOW)
    assert search.asked == [("What supply chain risks does Apple name?", ("AAPL",))]
    [system_message, user_message] = chat.prompts[0]
    assert "data, not instructions" in system_message.content
    assert f'<passage id="{passage_citation(0)}">' in user_message.content
    [record] = read_jsonl(results, Transcript)
    assert (record.system, record.model, [e.name for e in record.evidence]) == (
        "rag",
        "sim-chat",
        ["search_filings"],
    )


def test_rag_carries_earlier_turns_into_the_last_question(tmp_path: Path) -> None:
    search = FakeSearch()
    chat = ScriptedChat("SIMULATED first.", "SIMULATED second.")
    system = RagScenarios(search, chat, asked_on=ASKED_ON)
    run_scenarios([FOLLOW_UP], system, results=tmp_path / "rag.jsonl", now=lambda: NOW)
    assert [q for q, _ in search.asked] == ["Tell me about Apple.", "And its fiscal 2024 revenue?"]
    assert "SIMULATED first." in chat.prompts[1][1].content


def records(system: str, passed: dict[str, bool], facts: Evidence) -> list[Transcript]:
    text = {True: TRACED, False: "SIMULATED: no figure."}
    return [
        Transcript.model_validate(
            {
                "scenario_id": sid,
                "system": system,
                "model": "sim",
                "scenario_sha256": "0" * 64,
                "text": text[ok],
                "status": "answered",
                "evidence": (facts,),
                "asked_on": ASKED_ON,
                "answered_at": NOW,
            }
        )
        for sid, ok in passed.items()
    ]


def test_a1_report_scores_every_system_on_the_same_scenarios(facts_ctx: FactsContext) -> None:
    from faithfulness_kit import run_tool

    facts = run_tool(facts_ctx, "get_fact", company="AAPL", concept="revenue", fiscal_year=2024)
    scenarios = [VALUE, VALUE.model_copy(update={"id": "a1-009", "category": "ratio"})]
    report = agent_report(
        scenarios,
        {
            "rag": records("rag", {"a1-001": False}, facts),
            "agent": records("agent", {"a1-001": True, "a1-009": False}, facts),
        },
    )
    assert (report.scenarios, report.scored, report.missing) == (2, 1, {"rag": 1, "agent": 0})
    rag, agent = report.systems
    assert (rag.passed, rag.n, agent.passed, agent.n) == (0, 1, 1, 1)
    assert agent.by_category == {"value": (1, 1)}
    assert rag.failures == {"figure": 1}
    [comparison] = report.comparisons
    assert (comparison.system, comparison.other, comparison.result.a_only) == ("agent", "rag", 1)
    rows = agent_rows(report, split="test", date=ASKED_ON, git_sha="abc1234", index_version="v1")
    assert [(r.metric, r.system, r.n, r.cohort) for r in rows] == [
        ("A1", "rag", 1, "none"),
        ("A1", "agent", 1, "none"),
        ("A1_mcnemar_p", "agent_vs_rag", 1, "none"),
    ]


def test_a1_report_refuses_two_answers_to_one_scenario(facts_ctx: FactsContext) -> None:
    from faithfulness_kit import run_tool

    facts = run_tool(facts_ctx, "get_fact", company="AAPL", concept="revenue", fiscal_year=2024)
    twice = records("agent", {"a1-001": True}, facts) * 2
    with pytest.raises(ValueError, match="two answers"):
        agent_report([VALUE], {"agent": twice})
