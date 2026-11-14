"""A1 for a system without the XBRL tools: a correct, cited RAG answer passes.

The oracle results come from the real tools on the recorded Apple facts. Passages and
every answer text are simulated (they stand in for filing text and what a model writes).
"""

import datetime as dt
from collections.abc import Sequence
from pathlib import Path

import pytest
from faithfulness_kit import passage_citation, search_evidence

from sec_agent.agent.answer import Evidence
from sec_agent.agent.tool_runner import ToolRunner
from sec_agent.eval.agent.checks import check_scenario
from sec_agent.eval.agent.runner import run_scenarios
from sec_agent.eval.agent.scenarios import Scenario, ToolCheck, Transcript
from sec_agent.eval.agent.systems import RagScenarios, oracle_calls
from sec_agent.eval.numeric.baselines import Message
from sec_agent.golden.jsonl import read_jsonl
from sec_agent.tools.context import FactsContext

ASKED_ON = dt.date(2026, 11, 13)
NOW = dt.datetime(2026, 11, 13, 6, 0, tzinfo=dt.UTC)
RAG_TOOLS = ("search_filings",)
CONFIG = {"passages": 5, "facts": "v1", "space": "sim", "max_tokens": 1024}
REVENUE = ToolCheck(
    tool="get_fact",
    match={"company.ticker": "AAPL", "concept": "revenue", "fiscal_year": 2024},
    figure=r"fact\.value",
    call={"company": "AAPL", "concept": "revenue", "fiscal_year": 2024},
)
VALUE = Scenario.model_validate(
    {
        "id": "a1-001",
        "category": "value",
        "split": "test",
        "companies": ("AAPL",),
        "turns": ("What was Apple's revenue in fiscal 2024?",),
        "tools": (REVENUE,),
    }
)
PASSAGE = search_evidence("SIMULATED: Total net sales were $391,035 million in fiscal 2024.")


@pytest.fixture
def oracle(facts_ctx: FactsContext) -> tuple[Evidence, ...]:
    return oracle_calls(ToolRunner(facts_ctx))(VALUE)


def rag_transcript(text: str, oracle: tuple[Evidence, ...]) -> Transcript:
    return Transcript.model_validate(
        {
            "scenario_id": "a1-001",
            "system": "rag",
            "model": "sim",
            "scenario_sha256": "0" * 64,
            "text": text,
            "status": "answered",
            "evidence": (PASSAGE,),
            "asked_on": ASKED_ON,
            "answered_at": NOW,
            "offered_tools": RAG_TOOLS,
            "oracle": oracle,
        }
    )


def kinds(scenario: Scenario, transcript: Transcript) -> list[str]:
    return [f.kind for f in check_scenario(scenario, transcript).failures]


def test_the_oracle_is_the_checks_own_call(oracle: tuple[Evidence, ...]) -> None:
    [call] = oracle
    assert (call.call_id, call.name, call.ok) == ("oracle-0", "get_fact", True)
    assert '"value":"391035000000"' in call.result


def test_a_correct_cited_rag_figure_passes(oracle: tuple[Evidence, ...]) -> None:
    text = f"SIMULATED: Apple's revenue for fiscal 2024 was $391.0 billion [{passage_citation(0)}]."
    assert kinds(VALUE, rag_transcript(text, oracle)) == []


def test_a_rag_figure_must_be_the_oracles_value_and_period(
    facts_ctx: FactsContext,
) -> None:
    other_year = search_evidence("SIMULATED: Total net sales were $383,285 million in fiscal 2023.")
    oracle = oracle_calls(ToolRunner(facts_ctx))(VALUE)
    text = f"SIMULATED: Apple's revenue for fiscal 2023 was $383.3 billion [{passage_citation(0)}]."
    transcript = rag_transcript(text, oracle).model_copy(update={"evidence": (other_year,)})
    assert kinds(VALUE, transcript) == ["figure"]


def test_the_rag_figure_must_come_from_a_cited_passage(oracle: tuple[Evidence, ...]) -> None:
    uncited = "SIMULATED: Apple's revenue for fiscal 2024 was $391.0 billion."
    assert "figure" in kinds(VALUE, rag_transcript(uncited, oracle))


def test_without_an_oracle_the_figure_cannot_be_judged() -> None:
    text = f"SIMULATED: Apple's revenue for fiscal 2024 was $391.0 billion [{passage_citation(0)}]."
    assert kinds(VALUE, rag_transcript(text, ())) == ["oracle"]


def test_a_tool_only_check_without_a_figure_is_left_to_the_other_checks(
    oracle: tuple[Evidence, ...],
) -> None:
    """E12 for RAG: it cannot call get_fact; saying the figure is not reported suffices."""
    not_reported = VALUE.model_copy(
        update={
            "category": "not_reported",
            "tools": (ToolCheck(tool="get_fact", match={"status": "not_reported"}),),
            "says": (r"not reported",),
        }
    )
    assert kinds(not_reported, rag_transcript("SIMULATED: It is not reported.", oracle)) == []


def test_the_agent_still_needs_the_tool_call(oracle: tuple[Evidence, ...]) -> None:
    text = f"SIMULATED: Apple's revenue for fiscal 2024 was $391.0 billion [{passage_citation(0)}]."
    agent = rag_transcript(text, oracle).model_copy(
        update={"system": "agent", "offered_tools": None}
    )
    assert kinds(VALUE, agent) == ["tool"]


class OneChat:
    def __init__(self) -> None:
        self.asked = 0

    @property
    def name(self) -> str:
        return "sim-chat@max_tokens=1024"

    def complete(self, messages: Sequence[Message]) -> str:
        self.asked += 1
        return f"SIMULATED: $391.0 billion in fiscal 2024 [{passage_citation(0)}]."


def search(_query: str, _companies: tuple[str, ...]) -> Evidence:
    return PASSAGE


def test_a_rag_run_records_its_tools_and_the_oracle_and_rescores_right(
    facts_ctx: FactsContext, tmp_path: Path
) -> None:
    results = tmp_path / "rag.jsonl"
    rag = RagScenarios(search, OneChat(), asked_on=ASKED_ON, config=CONFIG)
    run_scenarios(
        [VALUE], rag, results=results, now=lambda: NOW, oracle=oracle_calls(ToolRunner(facts_ctx))
    )
    [record] = read_jsonl(results, Transcript)
    assert record.offered_tools == RAG_TOOLS
    assert [e.call_id for e in record.oracle] == ["oracle-0"]
    assert check_scenario(VALUE, record).passed


def test_changing_retrieval_or_generation_settings_asks_rag_again(tmp_path: Path) -> None:
    results = tmp_path / "rag.jsonl"
    chat = OneChat()
    for config in (CONFIG, CONFIG, CONFIG | {"passages": 8}, CONFIG | {"max_tokens": 6144}):
        rag = RagScenarios(search, chat, asked_on=ASKED_ON, config=config)
        run_scenarios([VALUE], rag, results=results, now=lambda: NOW)
    assert chat.asked == 3, "only the repeated settings were served from the cache"
