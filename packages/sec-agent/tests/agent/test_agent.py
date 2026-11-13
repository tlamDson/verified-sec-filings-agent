"""The agent loop: the model picks tools, code runs them, the model writes the answer.

The model is simulated (every reply is scripted by the test). The tools are real and read
the recorded Apple and NVIDIA facts, so the figures below are what SEC reported.
"""

import pytest
from agent_kit import APPLE_REVENUE_FY2024, ASKED_ON, agent_of, loads, roles, tool_messages
from llm_fakes import ScriptedProvider, call, calls, says

from sec_agent.agent.config import AgentConfig
from sec_agent.agent.errors import InvalidQuestionError, InvalidThreadError
from sec_agent.agent.notices import DEGRADED_TEXT, STEP_LIMIT_TEXT
from sec_agent.agent.prompt import system_prompt
from sec_agent.llm.errors import ProviderRateLimitedError, ProviderUnavailableError
from sec_agent.llm.messages import Usage
from sec_agent.tools.context import FactsContext

REVENUE = call("get_fact", "c1", company="AAPL", concept="revenue", fiscal_year=2024)
NET_INCOME = call("get_fact", "c2", company="AAPL", concept="net_income", fiscal_year=2024)
QUESTION = "What was Apple's revenue in fiscal 2024?"
ANSWER = "SIMULATED answer that quotes the tool result."
DOWN = ProviderUnavailableError("503 from provider")


def test_a_numeric_question_is_answered_from_a_tool_result(facts_ctx: FactsContext) -> None:
    model = ScriptedProvider("a", [calls(REVENUE), says(ANSWER)])
    answer = agent_of(facts_ctx, model).ask("t-1", QUESTION, asked_on=ASKED_ON)

    assert (answer.status, answer.text, answer.reason) == ("answered", ANSWER, None)
    assert (answer.thread_id, answer.turn, answer.asked_on) == ("t-1", 1, ASKED_ON)
    (evidence,) = answer.evidence
    assert (evidence.call_id, evidence.name, evidence.ok) == ("c1", "get_fact", True)
    assert loads(evidence.arguments) == {
        "company": "AAPL",
        "concept": "revenue",
        "fiscal_year": 2024,
    }
    assert loads(evidence.result)["fact"]["value"] == APPLE_REVENUE_FY2024
    assert loads(evidence.result)["fact"]["period_end"] == "2024-09-28"

    first, second = model.requests
    assert first.messages == [
        {"role": "system", "content": system_prompt(ASKED_ON)},
        {"role": "user", "content": QUESTION},
    ]
    assert [t["function"]["name"] for t in first.tools] == [
        "get_fact",
        "compute_ratio",
        "compare_peers",
    ]
    assert first.tool_choice == "auto"
    assert roles(second) == ["system", "user", "assistant", "tool"]
    (shown,) = tool_messages(second)
    assert shown.get("tool_call_id") == "c1"
    assert shown["content"] == evidence.result, "the model sees exactly what is kept as evidence"


def test_every_call_of_one_reply_is_run_in_order(facts_ctx: FactsContext) -> None:
    model = ScriptedProvider("a", [calls(REVENUE, NET_INCOME), says(ANSWER)])
    answer = agent_of(facts_ctx, model).ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert [e.call_id for e in answer.evidence] == ["c1", "c2"]
    assert [m.get("tool_call_id") for m in tool_messages(model.requests[1])] == ["c1", "c2"]
    assert loads(answer.evidence[1].result)["concept"] == "net_income"


def test_a_tool_refusal_goes_back_to_the_model_and_the_turn_goes_on(
    facts_ctx: FactsContext,
) -> None:
    """E7: a company outside the universe is a tool result the model reports, not a crash."""
    outside = call("get_fact", "c1", company="ZZZZ", concept="revenue", fiscal_year=2024)
    model = ScriptedProvider(
        "a", [calls(outside), says("SIMULATED: that company is out of scope.")]
    )
    answer = agent_of(facts_ctx, model).ask("t-1", "ZZZZ revenue?", asked_on=ASKED_ON)
    assert answer.status == "answered"
    (evidence,) = answer.evidence
    assert not evidence.ok
    assert loads(evidence.result)["error"]["code"] == "unknown_company"
    assert (
        loads(tool_messages(model.requests[1])[0]["content"])["error"]["code"] == "unknown_company"
    )


def test_the_last_allowed_call_must_answer_without_tools(facts_ctx: FactsContext) -> None:
    model = ScriptedProvider("a", [calls(REVENUE), calls(NET_INCOME), says(ANSWER)])
    agent = agent_of(facts_ctx, model, config=AgentConfig(max_llm_calls=3))
    answer = agent.ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert answer.status == "answered"
    assert [r.tool_choice for r in model.requests] == ["auto", "auto", "none"]
    assert len(answer.llm_calls) == 3


def test_a_model_that_never_stops_calling_tools_hits_the_step_limit(
    facts_ctx: FactsContext,
) -> None:
    model = ScriptedProvider("a", [calls(REVENUE), calls(NET_INCOME)])
    agent = agent_of(facts_ctx, model, config=AgentConfig(max_llm_calls=2))
    answer = agent.ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert (answer.status, answer.text) == ("step_limit", STEP_LIMIT_TEXT)
    assert [e.call_id for e in answer.evidence] == ["c1"], "the refused call was never run"

    model.then(says("SIMULATED follow-up answer."))
    follow_up = agent.ask("t-1", "And net income?", asked_on=ASKED_ON)
    assert follow_up.status == "answered"
    history = model.requests[-1].messages
    assert [m["role"] for m in history] == ["system", "user", "assistant", "user"]
    assert history[2] == {"role": "assistant", "content": STEP_LIMIT_TEXT}


def test_when_every_provider_fails_the_answer_is_degraded_and_says_so(
    facts_ctx: FactsContext,
) -> None:
    a = ScriptedProvider("a", [DOWN])
    b = ScriptedProvider("b", [ProviderRateLimitedError("429 from provider", retry_after=None)])
    answer = agent_of(facts_ctx, a, b).ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert (answer.status, answer.reason) == ("degraded", "llm_unavailable")
    assert answer.text == DEGRADED_TEXT
    assert answer.evidence == ()
    (failed,) = answer.llm_calls
    assert failed.provider is None
    assert (failed.prompt_tokens, failed.completion_tokens) == (0, 0)
    assert [(x.provider, x.outcome) for x in failed.attempts] == [
        ("a", "unavailable"),
        ("b", "rate_limited"),
    ]


def test_a_degraded_answer_keeps_the_tool_results_already_gathered(
    facts_ctx: FactsContext,
) -> None:
    """Plan: without the model, the deterministic figures are still returned."""
    model = ScriptedProvider("a", [calls(REVENUE), DOWN])
    agent = agent_of(facts_ctx, model)
    answer = agent.ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert (answer.status, answer.text) == ("degraded", DEGRADED_TEXT)
    (evidence,) = answer.evidence
    assert loads(evidence.result)["fact"]["value"] == APPLE_REVENUE_FY2024

    model.then(says(ANSWER))
    assert agent.ask("t-1", "Try again?", asked_on=ASKED_ON).status == "answered"
    assert model.requests[-1].messages[2] == {"role": "assistant", "content": DEGRADED_TEXT}


def test_a_reply_with_neither_text_nor_tool_calls_is_degraded(facts_ctx: FactsContext) -> None:
    model = ScriptedProvider("a", [says("")])
    answer = agent_of(facts_ctx, model).ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert (answer.status, answer.reason, answer.text) == ("degraded", "empty_reply", DEGRADED_TEXT)


def test_failover_shows_which_provider_answered_and_what_it_used(
    facts_ctx: FactsContext,
) -> None:
    a = ScriptedProvider("a", [DOWN])
    b = ScriptedProvider("b", [says(ANSWER)], usage=Usage(prompt_tokens=900, completion_tokens=31))
    answer = agent_of(facts_ctx, a, b).ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert answer.status == "answered"
    (used,) = answer.llm_calls
    assert (used.provider, used.model) == ("b", "sim-b")
    assert (used.prompt_tokens, used.completion_tokens) == (900, 31)
    assert [(x.provider, x.outcome, x.detail) for x in used.attempts] == [
        ("a", "unavailable", "503 from provider"),
        ("b", "ok", ""),
    ]


def test_a_follow_up_sees_the_earlier_question_and_answer_not_its_tool_calls(
    facts_ctx: FactsContext,
) -> None:
    model = ScriptedProvider(
        "a", [calls(REVENUE), says(ANSWER), calls(NET_INCOME), says("SIM second answer")]
    )
    agent = agent_of(facts_ctx, model)
    agent.ask("t-1", QUESTION, asked_on=ASKED_ON)
    follow_up = agent.ask("t-1", "And net income?", asked_on=ASKED_ON)
    assert follow_up.turn == 2
    assert [e.call_id for e in follow_up.evidence] == ["c2"], "only this turn's evidence"
    assert len(follow_up.llm_calls) == 2
    assert model.requests[2].messages[1:] == [
        {"role": "user", "content": QUESTION},
        {"role": "assistant", "content": ANSWER},
        {"role": "user", "content": "And net income?"},
    ]


def test_conversations_are_kept_apart(facts_ctx: FactsContext) -> None:
    model = ScriptedProvider("a", [says("one"), says("two")])
    agent = agent_of(facts_ctx, model)
    agent.ask("t-1", QUESTION, asked_on=ASKED_ON)
    other = agent.ask("t-2", "Another question", asked_on=ASKED_ON)
    assert other.turn == 1
    assert roles(model.requests[1]) == ["system", "user"]


@pytest.mark.parametrize("question", ["", "   ", "x" * 2001])
def test_an_empty_or_oversized_question_is_refused_before_any_call(
    facts_ctx: FactsContext, question: str
) -> None:
    model = ScriptedProvider("a")
    with pytest.raises(InvalidQuestionError):
        agent_of(facts_ctx, model).ask("t-1", question, asked_on=ASKED_ON)
    assert model.requests == []


def test_the_answer_length_limit_is_sent_to_the_model(facts_ctx: FactsContext) -> None:
    model = ScriptedProvider("a", [says(ANSWER)])
    agent_of(facts_ctx, model, config=AgentConfig(max_answer_tokens=256)).ask(
        "t-1", QUESTION, asked_on=ASKED_ON
    )
    assert model.requests[0].max_tokens == 256


@pytest.mark.parametrize("thread_id", ["", "  ", "t" * 201])
def test_an_empty_or_oversized_thread_id_is_refused_before_any_call(
    facts_ctx: FactsContext, thread_id: str
) -> None:
    model = ScriptedProvider("a")
    with pytest.raises(InvalidThreadError):
        agent_of(facts_ctx, model).ask(thread_id, QUESTION, asked_on=ASKED_ON)
    assert model.requests == []


def test_a_reply_cut_off_at_the_length_limit_is_not_shown(facts_ctx: FactsContext) -> None:
    """A reply cut in the middle could end in half a number."""
    model = ScriptedProvider(
        "a", [says("SIMULATED answer cut off at 391,03")], finish_reason="length"
    )
    answer = agent_of(facts_ctx, model).ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert (answer.status, answer.reason) == ("degraded", "truncated_reply")
    assert answer.text == DEGRADED_TEXT


def test_calls_beyond_the_limit_of_one_reply_are_refused_and_not_run(
    facts_ctx: FactsContext,
) -> None:
    many = [
        call("get_fact", f"c{i}", company="AAPL", concept="revenue", fiscal_year=2020 + i)
        for i in range(4)
    ]
    model = ScriptedProvider("a", [calls(*many), says(ANSWER)])
    agent = agent_of(facts_ctx, model, config=AgentConfig(max_tool_calls_per_reply=3))
    answer = agent.ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert answer.status == "answered"
    assert [e.ok for e in answer.evidence] == [True, True, True, False]
    assert loads(answer.evidence[3].result) == {
        "error": {"code": "too_many_calls", "message": "at most 3 tool calls in one reply"}
    }
    assert len(tool_messages(model.requests[1])) == 4, "every call still gets a result message"


@pytest.mark.parametrize(
    "field",
    ["max_llm_calls", "max_answer_tokens", "max_question_chars", "max_tool_calls_per_reply"],
)
def test_limits_must_be_positive(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        AgentConfig.model_validate({field: 0})


def test_one_llm_call_is_not_enough_to_use_a_tool() -> None:
    with pytest.raises(ValueError, match="max_llm_calls"):
        AgentConfig(max_llm_calls=1)
