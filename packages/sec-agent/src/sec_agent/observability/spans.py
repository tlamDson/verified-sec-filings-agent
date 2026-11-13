"""The spans of a turn, opened and closed with their attributes.

    invoke_agent sec-agent        the turn (`Agent.ask`, `Agent.steps`)
    ├─ llm_call                   one model call of the turn, failover included
    │  └─ chat                    one call to one provider (`LLMRouter`)
    └─ execute_tool <name>        one tool call

A provider the router passes over without calling it (breaker open, quota spent) is an
event on the model call, not a span: no call was made. Only names, counts, timings and
error codes are recorded, never the question, the answer or a tool result.
"""

from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer
from opentelemetry.util.types import Attributes

from sec_agent.llm.messages import ChatRequest, Completion
from sec_agent.observability import conventions as c

TRACER_NAME = "sec_agent"
MAX_TOOL_NAME_CHARS = 64
"""A tool name is written by the model; an unknown one is clipped to this length."""


def default_tracer() -> Tracer:
    """The tracer of the process's provider: a no-op until `setup.tracing` installs one."""
    return trace.get_tracer(TRACER_NAME)


def _turn_attributes(thread_id: str) -> Attributes:
    return {
        c.OPERATION: "invoke_agent",
        c.AGENT_NAME: c.AGENT,
        c.CONVERSATION_ID: thread_id,
        c.OI_SESSION_ID: thread_id,
        c.OI_SPAN_KIND: "AGENT",
        c.STEP: "turn",
    }


@contextmanager
def turn_span(tracer: Tracer, thread_id: str) -> Generator[Span]:
    name = f"invoke_agent {c.AGENT}"
    with _span(tracer, name, SpanKind.INTERNAL, _turn_attributes(thread_id)) as span:
        yield span


@contextmanager
def stepped_turn_span(
    tracer: Tracer, thread_id: str
) -> Generator[tuple[Span, Callable[[], AbstractContextManager[Span]]]]:
    """The span of a turn that is run step by step (`Agent.steps`), and a context manager
    that makes it the current span for one step.

    Unlike `turn_span` the span is not current for the whole block. The block is a
    generator that hands each step to its caller, and the caller may resume it on another
    thread, where a context entered earlier cannot be left. The span ends with the block;
    an exception that escapes, an abandoned generator included, marks it failed.
    """
    span = tracer.start_span(
        f"invoke_agent {c.AGENT}",
        kind=SpanKind.INTERNAL,
        attributes=_turn_attributes(thread_id),
        record_exception=False,
        set_status_on_exception=False,
    )

    def in_turn() -> AbstractContextManager[Span]:
        return trace.use_span(
            span, end_on_exit=False, record_exception=False, set_status_on_exception=False
        )

    try:
        yield span, in_turn
    except BaseException as error:
        failed(span, type(error).__name__)
        raise
    finally:
        span.end()


def turn_ended(span: Span, *, turn: int, status: str, reason: str | None) -> None:
    span.set_attribute(c.TURN, turn)
    span.set_attribute(c.TURN_STATUS, status)
    if reason is not None:
        span.set_attribute(c.TURN_REASON, reason)


@contextmanager
def llm_call_span(tracer: Tracer, *, tools_offered: bool) -> Generator[Span]:
    attributes: Attributes = {
        c.OI_SPAN_KIND: "CHAIN",
        c.STEP: "llm_call",
        c.TOOLS_OFFERED: tools_offered,
    }
    with _span(tracer, "llm_call", SpanKind.INTERNAL, attributes) as span:
        yield span


@contextmanager
def chat_span(tracer: Tracer, provider: str, request: ChatRequest) -> Generator[Span]:
    attributes: dict[str, str | int | float] = {
        c.OPERATION: "chat",
        c.PROVIDER: provider,
        c.REQUEST_TEMPERATURE: request.temperature,
        c.OI_SPAN_KIND: "LLM",
        c.OI_PROVIDER: provider,
        c.STEP: "chat",
    }
    if request.max_tokens is not None:
        attributes[c.REQUEST_MAX_TOKENS] = request.max_tokens
    with _span(tracer, "chat", SpanKind.CLIENT, attributes) as span:
        yield span


def chat_answered(span: Span, completion: Completion) -> None:
    usage = completion.usage
    span.set_attributes(
        {
            c.RESPONSE_MODEL: completion.model,
            c.RESPONSE_FINISH_REASONS: (completion.finish_reason,),
            c.INPUT_TOKENS: usage.prompt_tokens,
            c.OUTPUT_TOKENS: usage.completion_tokens,
            c.OI_MODEL: completion.model,
            c.OI_PROMPT_TOKENS: usage.prompt_tokens,
            c.OI_COMPLETION_TOKENS: usage.completion_tokens,
            c.OI_TOTAL_TOKENS: usage.total,
        }
    )


def provider_skipped(provider: str, outcome: str) -> None:
    """On the current span (the model call): the router passed over `provider`."""
    trace.get_current_span().add_event(
        c.SKIPPED_EVENT, {c.PROVIDER: provider, c.LLM_OUTCOME: outcome}
    )


@contextmanager
def tool_span(tracer: Tracer, name: str, call_id: str) -> Generator[Span]:
    name = name[:MAX_TOOL_NAME_CHARS]
    attributes: Attributes = {
        c.OPERATION: "execute_tool",
        c.TOOL_NAME: name,
        c.TOOL_CALL_ID: call_id[:MAX_TOOL_NAME_CHARS],
        c.TOOL_TYPE: "function",
        c.OI_SPAN_KIND: "TOOL",
        c.OI_TOOL_NAME: name,
        c.STEP: "tool",
    }
    with _span(tracer, f"execute_tool {name}", SpanKind.INTERNAL, attributes) as span:
        yield span


def failed(span: Span, error_type: str) -> None:
    """Mark a span failed with a code of ours (`error.type`) and no description: an
    error's text (a provider's, a tool's) is not exported, since it may quote a URL, a
    key or a response body."""
    span.set_attribute(c.ERROR_TYPE, error_type)
    span.set_status(Status(StatusCode.ERROR))


@contextmanager
def _span(tracer: Tracer, name: str, kind: SpanKind, attributes: Attributes) -> Generator[Span]:
    """A current span; an exception that escapes it marks it failed with its type."""
    with tracer.start_as_current_span(
        name,
        kind=kind,
        attributes=attributes,
        record_exception=False,  # an exception's text may quote what the user asked
        set_status_on_exception=False,
    ) as span:
        try:
            yield span
        except BaseException as error:
            failed(span, type(error).__name__)
            raise
