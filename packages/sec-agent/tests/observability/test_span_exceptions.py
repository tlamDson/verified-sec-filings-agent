"""An exception that escapes a span: the span says its type and exports none of its text.

An exception's message or stack trace may quote what the user asked, a URL or a key, so
neither may reach Phoenix or the span file. Spans stay in memory (`trace_kit.Traces`).
"""

from collections.abc import Callable
from contextlib import AbstractContextManager

import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import Span, StatusCode, Tracer
from trace_kit import Traces, attrs

from sec_agent.llm.messages import ChatRequest
from sec_agent.observability.spans import chat_span, llm_call_span, tool_span, turn_span

MARKER = "SECRET-QUESTION"

OpenSpan = Callable[[Tracer], AbstractContextManager[Span]]

SPANS: dict[str, OpenSpan] = {
    "turn": lambda tracer: turn_span(tracer, "t-1"),
    "llm_call": lambda tracer: llm_call_span(tracer, tools_offered=True),
    "chat": lambda tracer: chat_span(tracer, "a", ChatRequest(messages=())),
    "tool": lambda tracer: tool_span(tracer, "get_fact", "c1"),
}


def exported_text(span: ReadableSpan) -> list[str]:
    """Every string a span exports: name, status, attributes, events and their attributes."""
    return [
        span.name,
        str(span.status.description),
        *(f"{key}={value}" for key, value in attrs(span).items()),
        *(event.name for event in span.events),
        *(
            f"{key}={value}"
            for event in span.events
            for key, value in (event.attributes or {}).items()
        ),
    ]


@pytest.mark.parametrize("step", sorted(SPANS))
def test_an_exception_escaping_a_span_exports_its_type_and_none_of_its_text(step: str) -> None:
    traces = Traces()
    with pytest.raises(RuntimeError, match=MARKER), SPANS[step](traces.tracer):
        raise RuntimeError(f"{MARKER} could not be parsed")

    span = traces.one(step)
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description is None, "the exception's text is not the status"
    assert attrs(span)["error.type"] == "RuntimeError"
    assert not span.events, "no exception event: it would hold the message and the stack trace"
    assert not [text for text in exported_text(span) if MARKER in text]
    assert not [text for text in exported_text(span) if "Traceback" in text or ".py" in text]


def test_an_exception_escaping_nested_spans_marks_each_of_them() -> None:
    traces = Traces()
    with (
        pytest.raises(KeyError),
        turn_span(traces.tracer, "t-1"),
        llm_call_span(traces.tracer, tools_offered=False),
        chat_span(traces.tracer, "a", ChatRequest(messages=())),
    ):
        raise KeyError(MARKER)

    spans = traces.spans()
    assert [attrs(s)["sec_agent.step"] for s in spans] == ["chat", "llm_call", "turn"]
    assert [attrs(s)["error.type"] for s in spans] == ["KeyError"] * 3
    assert all(s.status.status_code == StatusCode.ERROR for s in spans)
    assert not [text for s in spans for text in exported_text(s) if MARKER in text]


def test_a_span_that_ends_without_an_exception_is_not_marked() -> None:
    traces = Traces()
    with tool_span(traces.tracer, "get_fact", "c1"):
        pass

    span = traces.one("tool")
    assert span.status.status_code == StatusCode.UNSET
    assert "error.type" not in attrs(span)
