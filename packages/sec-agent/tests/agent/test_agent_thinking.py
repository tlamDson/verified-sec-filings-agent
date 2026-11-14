"""Which role each model call of a turn asks for (it picks the thinking setting)."""

from agent_kit import ASKED_ON, agent_of
from llm_fakes import ScriptedProvider, call, calls, says

from sec_agent.agent.config import AgentConfig
from sec_agent.tools.context import FactsContext

REVENUE = call("get_fact", "c1", company="AAPL", concept="revenue", fiscal_year=2024)
QUESTION = "What was Apple's revenue in fiscal 2024?"


def test_a_call_that_may_use_tools_is_tool_choice_and_the_last_one_is_the_answer(
    facts_ctx: FactsContext,
) -> None:
    model = ScriptedProvider("a", [calls(REVENUE), says("SIMULATED answer.")])
    agent = agent_of(facts_ctx, model, config=AgentConfig(max_llm_calls=2))
    agent.ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert [r.tool_choice for r in model.requests] == ["auto", "none"]
    assert [r.role for r in model.requests] == ["tool_choice", "answer"]
