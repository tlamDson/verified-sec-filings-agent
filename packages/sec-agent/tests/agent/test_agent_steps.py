"""`Agent.steps`: a turn as it happens, for a caller that streams it.

The model is simulated (every reply is scripted by the test); the tools are real and read
the recorded Apple and NVIDIA facts. Spans stay in memory (`trace_kit.Traces`).
"""

import logging
from concurrent.futures import ThreadPoolExecutor

import pytest
from agent_kit import APPLE_REVENUE_FY2024, ASKED_ON, agent_of, loads
from llm_fakes import ScriptedProvider, call, calls, says
from opentelemetry.trace import StatusCode
from trace_kit import Traces, attrs, parent_id, span_id

from sec_agent.agent.answer import Answer, Evidence
from sec_agent.agent.errors import InvalidQuestionError
from sec_agent.llm.errors import ProviderUnavailableError
from sec_agent.tools.context import FactsContext

REVENUE = call("get_fact", "c1", company="AAPL", concept="revenue", fiscal_year=2024)
NET_INCOME = call("get_fact", "c2", company="AAPL", concept="net_income", fiscal_year=2024)
GROSS_PROFIT = call("get_fact", "c3", company="AAPL", concept="gross_profit", fiscal_year=2024)
QUESTION = "What was Apple's revenue in fiscal 2024?"
ANSWER = "SIMULATED answer that quotes the tool result."


def test_each_tool_result_is_yielded_before_the_model_is_called_again(
    facts_ctx: FactsContext,
) -> None:
    model = ScriptedProvider("a", [calls(REVENUE, NET_INCOME), calls(GROSS_PROFIT), says(ANSWER)])
    steps = agent_of(facts_ctx, model).steps("t-1", QUESTION, asked_on=ASKED_ON)

    first, second = next(steps), next(steps)
    assert isinstance(first, Evidence)
    assert isinstance(second, Evidence)
    assert (first.call_id, second.call_id) == ("c1", "c2")
    assert loads(first.result)["fact"]["value"] == APPLE_REVENUE_FY2024
    assert len(model.requests) == 1, "the first results are out before the second model call"

    third = next(steps)
    assert isinstance(third, Evidence)
    assert third.call_id == "c3"
    assert len(model.requests) == 2

    answer = next(steps)
    assert isinstance(answer, Answer)
    assert (answer.status, answer.text, answer.turn) == ("answered", ANSWER, 1)
    assert answer.evidence == (first, second, third)
    assert list(steps) == []


def test_the_last_step_is_the_answer_ask_returns(facts_ctx: FactsContext) -> None:
    script = [calls(REVENUE), says(ANSWER)]
    asked = agent_of(facts_ctx, ScriptedProvider("a", script)).ask(
        "t-1", QUESTION, asked_on=ASKED_ON
    )
    *_, stepped = agent_of(facts_ctx, ScriptedProvider("a", script)).steps(
        "t-1", QUESTION, asked_on=ASKED_ON
    )
    assert stepped == asked


def test_a_later_turn_does_not_repeat_the_evidence_of_an_earlier_one(
    facts_ctx: FactsContext,
) -> None:
    model = ScriptedProvider("a", [calls(REVENUE), says(ANSWER), says("SIMULATED follow-up.")])
    agent = agent_of(facts_ctx, model)
    assert len(list(agent.steps("t-1", QUESTION, asked_on=ASKED_ON))) == 2
    (answer,) = agent.steps("t-1", "And what else?", asked_on=ASKED_ON)
    assert isinstance(answer, Answer)
    assert (answer.turn, answer.evidence) == (2, ())


def test_a_degraded_turn_ends_with_its_answer_too(facts_ctx: FactsContext) -> None:
    model = ScriptedProvider("a", [calls(REVENUE), ProviderUnavailableError("503 from provider")])
    evidence, answer = agent_of(facts_ctx, model).steps("t-1", QUESTION, asked_on=ASKED_ON)
    assert isinstance(evidence, Evidence)
    assert isinstance(answer, Answer)
    assert (answer.status, answer.evidence) == ("degraded", (evidence,))


def test_an_invalid_question_is_refused_before_any_step(facts_ctx: FactsContext) -> None:
    model = ScriptedProvider("a", [says(ANSWER)])
    steps = agent_of(facts_ctx, model).steps("t-1", "   ", asked_on=ASKED_ON)
    with pytest.raises(InvalidQuestionError):
        next(steps)
    assert model.requests == []


def _turn_children(traces: Traces) -> list[str]:
    """The steps directly under the turn's span, in the order they ended."""
    turn = traces.one("turn")
    return [
        str(attrs(s)["sec_agent.step"]) for s in traces.spans() if parent_id(s) == span_id(turn)
    ]


def test_a_stepped_turn_is_one_trace_like_an_asked_one(facts_ctx: FactsContext) -> None:
    traces = Traces()
    model = ScriptedProvider("a", [calls(REVENUE), says(ANSWER)])
    agent = agent_of(facts_ctx, model, tracer=traces.tracer)
    list(agent.steps("t-1", QUESTION, asked_on=ASKED_ON))

    turn = traces.one("turn")
    assert parent_id(turn) is None
    assert len({s.context.trace_id for s in traces.spans() if s.context}) == 1
    assert _turn_children(traces) == ["llm_call", "tool", "llm_call"]
    assert attrs(turn)["gen_ai.conversation.id"] == "t-1"
    assert (attrs(turn)["sec_agent.turn"], attrs(turn)["sec_agent.turn.status"]) == (1, "answered")
    assert turn.status.status_code == StatusCode.UNSET


def test_steps_taken_on_different_threads_stay_in_the_turns_trace(
    facts_ctx: FactsContext, caplog: pytest.LogCaptureFixture
) -> None:
    """A streaming server takes each item on whichever worker thread is free."""
    traces = Traces()
    model = ScriptedProvider("a", [calls(REVENUE), calls(NET_INCOME), says(ANSWER)])
    steps = agent_of(facts_ctx, model, tracer=traces.tracer).steps(
        "t-1", QUESTION, asked_on=ASKED_ON
    )
    taken: list[Evidence | Answer] = []
    with caplog.at_level(logging.ERROR, logger="opentelemetry"):
        while True:
            with ThreadPoolExecutor(max_workers=1) as one_thread:
                item = one_thread.submit(next, steps, None).result()
            if item is None:
                break
            taken.append(item)

    assert [type(item) for item in taken] == [Evidence, Evidence, Answer]
    assert len({s.context.trace_id for s in traces.spans() if s.context}) == 1
    assert _turn_children(traces) == ["llm_call", "tool", "llm_call", "tool", "llm_call"]
    assert caplog.records == [], "no context was left on a thread that did not enter it"


def test_a_stepped_turn_that_is_abandoned_ends_its_span_as_failed(
    facts_ctx: FactsContext,
) -> None:
    traces = Traces()
    model = ScriptedProvider("a", [calls(REVENUE), says(ANSWER)])
    steps = agent_of(facts_ctx, model, tracer=traces.tracer).steps(
        "t-1", QUESTION, asked_on=ASKED_ON
    )
    next(steps)
    steps.close()  # the client went away before the answer

    turn = traces.one("turn")
    assert turn.status.status_code == StatusCode.ERROR
    assert attrs(turn)["error.type"] == "GeneratorExit"
    assert "sec_agent.turn.status" not in attrs(turn)
    assert len(model.requests) == 1, "the model was not called again"
