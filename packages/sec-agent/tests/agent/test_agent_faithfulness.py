"""The checker between the model's draft and the user: what is shown, kept and remembered.

The model is simulated (every reply is scripted); the tools read the recorded Apple facts.
"""

from agent_kit import ASKED_ON, agent_of
from llm_fakes import ScriptedProvider, call, calls, says

from sec_agent.agent.config import AgentConfig
from sec_agent.agent.notices import DEGRADED_TEXT
from sec_agent.faithfulness.notices import BLOCKED_TEXT, TRIMMED_NOTE
from sec_agent.llm.errors import ProviderUnavailableError
from sec_agent.tools.context import FactsContext

REVENUE = call("get_fact", "c1", company="AAPL", concept="revenue", fiscal_year=2024)
QUESTION = "What was Apple's revenue in fiscal 2024?"
TRACED = "SIMULATED: Apple's revenue for fiscal 2024 was $391.0 billion."
INVENTED = "SIMULATED: Apple's revenue for fiscal 2024 was $412.7 billion."
FORECAST = "SIMULATED: it will reach $450 billion next year."


def test_an_answer_whose_figures_trace_is_shown_as_written(facts_ctx: FactsContext) -> None:
    model = ScriptedProvider("a", [calls(REVENUE), says(TRACED)])
    answer = agent_of(facts_ctx, model).ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert (answer.status, answer.text, answer.draft) == ("answered", TRACED, TRACED)
    assert answer.faithfulness is not None
    assert (answer.faithfulness.verdict, answer.faithfulness.faithful) == ("pass", True)


def test_an_invented_figure_blocks_the_answer_and_the_evidence_is_still_returned(
    facts_ctx: FactsContext,
) -> None:
    model = ScriptedProvider("a", [calls(REVENUE), says(INVENTED)])
    answer = agent_of(facts_ctx, model).ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert (answer.status, answer.reason, answer.text) == (
        "blocked",
        "untraced_figures",
        BLOCKED_TEXT,
    )
    assert answer.draft == INVENTED, "the draft is kept for the record, not shown"
    assert answer.faithfulness is not None
    assert answer.faithfulness.verdict == "blocked"
    assert [e.call_id for e in answer.evidence] == ["c1"]


def test_a_follow_up_sees_what_the_user_was_shown_not_the_draft(facts_ctx: FactsContext) -> None:
    model = ScriptedProvider(
        "a", [calls(REVENUE), says(f"{TRACED} {FORECAST}"), says("SIMULATED follow-up.")]
    )
    agent = agent_of(facts_ctx, model)
    first = agent.ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert first.status == "answered"
    assert first.text == f"{TRACED}\n\n{TRIMMED_NOTE}"
    assert first.faithfulness is not None
    assert first.faithfulness.verdict == "trimmed"

    agent.ask("t-1", "And next year?", asked_on=ASKED_ON)
    assert model.requests[-1].messages[2] == {"role": "assistant", "content": first.text}


def test_without_the_checker_the_draft_is_shown_unchecked(facts_ctx: FactsContext) -> None:
    """The N2 baseline: the agent without its checker."""
    model = ScriptedProvider("a", [calls(REVENUE), says(INVENTED)])
    agent = agent_of(facts_ctx, model, config=AgentConfig(faithfulness=None))
    answer = agent.ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert (answer.status, answer.text, answer.draft) == ("answered", INVENTED, INVENTED)
    assert answer.faithfulness is None


def test_a_degraded_turn_has_no_draft_to_check(facts_ctx: FactsContext) -> None:
    model = ScriptedProvider("a", [ProviderUnavailableError("503 from provider")])
    answer = agent_of(facts_ctx, model).ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert (answer.status, answer.text) == ("degraded", DEGRADED_TEXT)
    assert (answer.draft, answer.faithfulness) == (None, None)
