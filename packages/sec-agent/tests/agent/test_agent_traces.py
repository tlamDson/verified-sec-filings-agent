"""One OpenTelemetry trace per turn: the turn, each model call, each provider call, each tool.

The model is simulated (`ScriptedProvider`); spans stay in memory (`trace_kit.Traces`).
"""

import pytest
from agent_kit import ASKED_ON, agent_of
from llm_fakes import ScriptedProvider, call, calls, says
from opentelemetry.trace import SpanKind, StatusCode
from trace_kit import Traces, attrs, parent_id, span_id

from sec_agent.llm.errors import (
    ProviderRateLimitedError,
    ProviderRejectedError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from sec_agent.llm.messages import Usage
from sec_agent.tools.context import FactsContext

REVENUE = call("get_fact", "c1", company="AAPL", concept="revenue", fiscal_year=2024)
OUTSIDE = call("get_fact", "c2", company="ZZZZ", concept="revenue", fiscal_year=2024)
QUESTION = "What was Apple's revenue in fiscal 2024?"
ANSWER = "SIMULATED answer that quotes the tool result."


def test_a_turn_is_one_trace_with_a_span_per_step(facts_ctx: FactsContext) -> None:
    traces = Traces()
    model = ScriptedProvider("a", [calls(REVENUE), says(ANSWER)])
    agent_of(facts_ctx, model, tracer=traces.tracer).ask("t-1", QUESTION, asked_on=ASKED_ON)

    turn = traces.one("turn")
    assert parent_id(turn) is None
    assert len({s.context.trace_id for s in traces.spans() if s.context}) == 1
    llm_steps = traces.step("llm_call")
    (tool,) = traces.step("tool")
    assert len(llm_steps) == 2
    assert all(parent_id(s) == span_id(turn) for s in [*llm_steps, tool])
    chats = traces.step("chat")
    assert [parent_id(c) for c in chats] == [span_id(s) for s in llm_steps]
    assert turn.name == "invoke_agent sec-agent"
    assert turn.kind == SpanKind.INTERNAL
    assert attrs(turn) == {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": "sec-agent",
        "gen_ai.conversation.id": "t-1",
        "session.id": "t-1",
        "openinference.span.kind": "AGENT",
        "sec_agent.step": "turn",
        "sec_agent.turn": 1,
        "sec_agent.turn.status": "answered",
    }
    assert turn.status.status_code == StatusCode.UNSET


def test_a_provider_call_carries_the_genai_and_phoenix_attributes(
    facts_ctx: FactsContext,
) -> None:
    traces = Traces()
    model = ScriptedProvider(
        "a", [says(ANSWER)], usage=Usage(prompt_tokens=120, completion_tokens=30)
    )
    agent_of(facts_ctx, model, tracer=traces.tracer).ask("t-1", QUESTION, asked_on=ASKED_ON)

    chat = traces.one("chat")
    assert chat.name == "chat"
    assert chat.kind == SpanKind.CLIENT
    assert attrs(chat) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "a",
        "gen_ai.request.max_tokens": 1024,
        "gen_ai.request.temperature": 0.0,
        "gen_ai.response.model": "sim-a",
        "gen_ai.response.finish_reasons": ("stop",),
        "gen_ai.usage.input_tokens": 120,
        "gen_ai.usage.output_tokens": 30,
        "openinference.span.kind": "LLM",
        "llm.provider": "a",
        "llm.model_name": "sim-a",
        "llm.token_count.prompt": 120,
        "llm.token_count.completion": 30,
        "llm.token_count.total": 150,
        "sec_agent.step": "chat",
    }
    step = traces.one("llm_call")
    assert step.name == "llm_call"
    assert attrs(step) == {
        "openinference.span.kind": "CHAIN",
        "sec_agent.step": "llm_call",
        "sec_agent.llm.tools_offered": True,
    }


def test_failover_shows_one_provider_span_per_call_made(facts_ctx: FactsContext) -> None:
    traces = Traces()
    a = ScriptedProvider("a", [ProviderUnavailableError("503 from provider")])
    b = ScriptedProvider("b", [says(ANSWER)])
    agent_of(facts_ctx, a, b, tracer=traces.tracer).ask("t-1", QUESTION, asked_on=ASKED_ON)

    failed, answered = traces.step("chat")
    assert attrs(failed)["gen_ai.provider.name"] == "a"
    assert attrs(failed)["error.type"] == "unavailable"
    assert failed.status.status_code == StatusCode.ERROR
    assert failed.status.description is None, "the error's text is not exported"
    assert "gen_ai.usage.input_tokens" not in attrs(failed)
    assert attrs(answered)["gen_ai.provider.name"] == "b"
    assert answered.status.status_code == StatusCode.UNSET
    assert traces.one("llm_call").status.status_code == StatusCode.UNSET


def test_a_degraded_turn_marks_the_model_step_and_the_turn(facts_ctx: FactsContext) -> None:
    traces = Traces()
    model = ScriptedProvider("a", [ProviderUnavailableError("503 from provider")])
    agent_of(facts_ctx, model, tracer=traces.tracer).ask("t-1", QUESTION, asked_on=ASKED_ON)

    step = traces.one("llm_call")
    assert step.status.status_code == StatusCode.ERROR
    assert attrs(step)["error.type"] == "llm_unavailable"
    turn = traces.one("turn")
    assert attrs(turn)["sec_agent.turn.status"] == "degraded"
    assert attrs(turn)["sec_agent.turn.reason"] == "llm_unavailable"


def test_a_provider_the_router_skips_is_an_event_not_a_call(facts_ctx: FactsContext) -> None:
    """A provider whose breaker is open makes no call: no chat span, one event."""
    traces = Traces()
    a = ScriptedProvider("a", [ProviderUnavailableError("503")] * 3)
    b = ScriptedProvider("b", [says(ANSWER)] * 4)
    agent = agent_of(facts_ctx, a, b, tracer=traces.tracer)
    for n in range(4):  # three failures in a row open the breaker of `a`
        agent.ask(f"t-{n}", QUESTION, asked_on=ASKED_ON)

    last_step = traces.step("llm_call")[-1]
    last_chats = [c for c in traces.step("chat") if parent_id(c) == span_id(last_step)]
    assert [attrs(c)["gen_ai.provider.name"] for c in last_chats] == ["b"]
    (event,) = last_step.events
    assert event.name == "sec_agent.llm.skipped"
    assert dict(event.attributes or {}) == {
        "gen_ai.provider.name": "a",
        "sec_agent.llm.outcome": "breaker_open",
    }


def test_each_tool_call_is_a_span_and_a_refusal_is_an_error(facts_ctx: FactsContext) -> None:
    traces = Traces()
    model = ScriptedProvider("a", [calls(REVENUE, OUTSIDE), says(ANSWER)])
    agent_of(facts_ctx, model, tracer=traces.tracer).ask("t-1", QUESTION, asked_on=ASKED_ON)

    ok, refused = traces.step("tool")
    assert ok.name == "execute_tool get_fact"
    assert attrs(ok) == {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": "get_fact",
        "gen_ai.tool.call.id": "c1",
        "gen_ai.tool.type": "function",
        "openinference.span.kind": "TOOL",
        "tool.name": "get_fact",
        "sec_agent.step": "tool",
    }
    assert ok.status.status_code == StatusCode.UNSET
    assert attrs(refused)["gen_ai.tool.call.id"] == "c2"
    assert attrs(refused)["error.type"] == "unknown_company"
    assert refused.status.status_code == StatusCode.ERROR


def test_no_span_records_the_question_the_answer_or_a_tool_result(
    facts_ctx: FactsContext,
) -> None:
    """Content is not captured: traces hold metadata, so Phoenix holds no user text."""
    traces = Traces()
    model = ScriptedProvider("a", [calls(REVENUE), says(ANSWER)])
    agent_of(facts_ctx, model, tracer=traces.tracer).ask("t-1", QUESTION, asked_on=ASKED_ON)

    values = [str(v) for s in traces.spans() for v in attrs(s).values()]
    values += [
        str(v) for s in traces.spans() for e in s.events for v in (e.attributes or {}).values()
    ]
    assert not [v for v in values if "Apple" in v or "SIMULATED" in v or "391035" in v]


@pytest.mark.parametrize(
    "error",
    [
        ProviderUnavailableError("SECRET-TEXT timed out"),
        ProviderRateLimitedError("SECRET-TEXT 429", retry_after=None),
        ProviderRejectedError("SECRET-TEXT 401"),
        ProviderResponseError("SECRET-TEXT body"),
    ],
)
def test_no_span_exports_the_text_of_a_provider_error(
    facts_ctx: FactsContext, error: Exception
) -> None:
    """A provider's error text is not ours to export (it may quote a URL, a key or a body):
    the span says what happened with the router's outcome code only."""
    traces = Traces()
    a = ScriptedProvider("a", [error])
    b = ScriptedProvider("b", [says(ANSWER)])
    agent_of(facts_ctx, a, b, tracer=traces.tracer).ask("t-1", QUESTION, asked_on=ASKED_ON)

    exported = [
        *(str(s.status.description) for s in traces.spans()),
        *(str(v) for s in traces.spans() for v in attrs(s).values()),
        *(str(v) for s in traces.spans() for e in s.events for v in (e.attributes or {}).values()),
        *(e.name for s in traces.spans() for e in s.events),
    ]
    assert not [v for v in exported if "SECRET-TEXT" in v]
    failed, _ = traces.step("chat")
    assert failed.status.status_code == StatusCode.ERROR
    assert attrs(failed)["error.type"] != ""


def test_an_agent_without_a_tracer_still_answers(facts_ctx: FactsContext) -> None:
    model = ScriptedProvider("a", [says(ANSWER)])
    answer = agent_of(facts_ctx, model).ask("t-1", QUESTION, asked_on=ASKED_ON)
    assert answer.status == "answered"
