"""A cached agent answer is reused only by the same agent (the stale-cache finding of s-12).

The model is simulated (scripted replies); the tools read the recorded Apple facts.
"""

import datetime as dt
from pathlib import Path

from agent_kit import agent_of
from eval_data import number_question
from llm_fakes import ScriptedProvider, says

from sec_agent.agent.config import AgentConfig
from sec_agent.agent.tool_runner import ToolRunner
from sec_agent.eval.fingerprint import agent_fingerprint
from sec_agent.eval.numeric.agent_model import AgentChatModel
from sec_agent.eval.numeric.baselines import B2
from sec_agent.eval.numeric.runner import run_numeric
from sec_agent.golden.gnum.models import NumQuestion
from sec_agent.tools.context import FactsContext

ASKED_ON = dt.date(2026, 11, 13)
NOW = dt.datetime(2026, 11, 13, 5, 0, tzinfo=dt.UTC)
PINS = {"facts": "v1", "snapshot": "v1", "reranker": "none"}


def fingerprint(tools: ToolRunner, **changes: object) -> str:
    base: dict[str, object] = {
        "asked_on": ASKED_ON,
        "config": AgentConfig(),
        "tools": tools,
        "pins": PINS,
    }
    return agent_fingerprint(**(base | changes))  # pyright: ignore[reportArgumentType]


def test_the_fingerprint_changes_with_everything_an_answer_depends_on(
    facts_ctx: FactsContext,
) -> None:
    tools = ToolRunner(facts_ctx)
    same = fingerprint(tools)
    assert same == fingerprint(ToolRunner(facts_ctx))
    assert (
        len(
            {
                same,
                fingerprint(tools, asked_on=dt.date(2026, 11, 14)),
                fingerprint(tools, config=AgentConfig(max_answer_tokens=6144)),
                fingerprint(tools, config=AgentConfig(faithfulness=None)),
                fingerprint(tools, pins=PINS | {"facts": "v2"}),
                fingerprint(tools, pins=PINS | {"reranker": "models/rerank-v1"}),
            }
        )
        == 6
    )


def test_a_changed_agent_asks_again_instead_of_reusing_the_cache(
    facts_ctx: FactsContext, tmp_path: Path
) -> None:
    question: NumQuestion = number_question("revenue", "1")
    provider = ScriptedProvider("a", [says("SIMULATED one."), says("SIMULATED two.")])
    agent = agent_of(facts_ctx, provider)
    results = tmp_path / "b2.jsonl"
    before = AgentChatModel(agent, name="agent:sim", asked_on=ASKED_ON, fingerprint="aaaa")
    after = AgentChatModel(agent, name="agent:sim", asked_on=ASKED_ON, fingerprint="bbbb")
    assert run_numeric([question], B2(), before, results=results, now=lambda: NOW).asked == 1
    assert run_numeric([question], B2(), before, results=results, now=lambda: NOW).cached == 1
    assert run_numeric([question], B2(), after, results=results, now=lambda: NOW).asked == 1
