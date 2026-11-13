"""The JSONL span file: what the latency table reads, written next to the Phoenix export."""

from pathlib import Path

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace import StatusCode

from sec_agent.observability.span_file import (
    JsonlSpanExporter,
    SpanFileError,
    SpanRecord,
    read_spans,
)


def _provider(path: Path) -> TracerProvider:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(JsonlSpanExporter(path)))
    return provider


def test_finished_spans_are_appended_one_json_object_per_line(tmp_path: Path) -> None:
    path = tmp_path / "traces" / "spans.jsonl"
    provider = _provider(path)
    tracer = provider.get_tracer("tests")
    with (
        tracer.start_as_current_span("parent", attributes={"sec_agent.step": "turn"}),
        tracer.start_as_current_span("child") as child,
    ):
        child.set_attribute("gen_ai.usage.input_tokens", 12)
        child.set_attribute("gen_ai.response.finish_reasons", ("stop",))
        child.set_status(StatusCode.ERROR, "503")
    provider.shutdown()

    assert len(path.read_text("utf-8").splitlines()) == 2
    child_record, parent_record = read_spans(path)
    assert (child_record.name, parent_record.name) == ("child", "parent")
    assert child_record.trace_id == parent_record.trace_id
    assert len(child_record.trace_id) == 32
    assert len(child_record.span_id) == 16
    assert child_record.parent_id == parent_record.span_id
    assert parent_record.parent_id is None
    assert child_record.status == "error"
    assert parent_record.status == "unset"
    assert child_record.attributes == {
        "gen_ai.usage.input_tokens": 12,
        "gen_ai.response.finish_reasons": ["stop"],
    }
    assert parent_record.start_ns <= child_record.start_ns <= child_record.end_ns
    assert child_record.end_ns <= parent_record.end_ns


def test_a_second_process_appends_to_the_same_file(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    for name in ("first", "second"):
        provider = _provider(path)
        with provider.get_tracer("tests").start_as_current_span(name):
            pass
        provider.shutdown()
    assert [r.name for r in read_spans(path)] == ["first", "second"]


def test_duration_is_in_milliseconds() -> None:
    record = SpanRecord(
        trace_id="0" * 31 + "1",
        span_id="0" * 15 + "1",
        parent_id=None,
        name="x",
        start_ns=1_000_000,
        end_ns=3_500_000,
        status="unset",
        attributes={},
    )
    assert record.duration_ms == 2.5


def test_a_malformed_line_names_its_line_number(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    provider = _provider(path)
    with provider.get_tracer("tests").start_as_current_span("ok"):
        pass
    provider.shutdown()
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n{not json\n")
    with pytest.raises(SpanFileError, match="line 3"):
        read_spans(path)


def test_a_span_that_ends_before_it_starts_is_refused() -> None:
    with pytest.raises(ValueError, match="ends before it starts"):
        SpanRecord(
            trace_id="0" * 31 + "1",
            span_id="0" * 15 + "1",
            parent_id=None,
            name="x",
            start_ns=5,
            end_ns=4,
            status="unset",
            attributes={},
        )


def test_a_missing_file_is_a_span_file_error(tmp_path: Path) -> None:
    with pytest.raises(SpanFileError, match="no span file"):
        read_spans(tmp_path / "absent.jsonl")
