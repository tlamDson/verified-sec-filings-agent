"""Hand-built span records for the latency table tests (simulated timings, not measured)."""

from typing import Any

from sec_agent.observability.span_file import SpanRecord

MS = 1_000_000


class Trace:
    """One simulated trace: spans added in order, each with a start and length in ms."""

    def __init__(self, number: int) -> None:
        self.trace_id = f"{number:032x}"
        self._next = 1
        self.records: list[SpanRecord] = []

    def span(
        self,
        step: str,
        start_ms: float,
        length_ms: float,
        *,
        parent: SpanRecord | None = None,
        status: str = "unset",
        **attributes: Any,
    ) -> SpanRecord:
        record = SpanRecord(
            trace_id=self.trace_id,
            span_id=f"{int(self.trace_id, 16) * 1000 + self._next:016x}",
            parent_id=parent.span_id if parent is not None else None,
            name=step,
            start_ns=int(start_ms * MS),
            end_ns=int((start_ms + length_ms) * MS),
            status=status,  # pyright: ignore[reportArgumentType]
            attributes={"sec_agent.step": step, **attributes},
        )
        self._next += 1
        self.records.append(record)
        return record


def turn_trace(
    number: int,
    *,
    turn_ms: float,
    llm_ms: tuple[float, ...],
    tool_ms: tuple[float, ...] = (),
    tokens: tuple[tuple[int, int], ...] = (),
    provider: str = "a",
) -> list[SpanRecord]:
    """A turn with its model calls (one provider call each) and its tools, back to back."""
    trace = Trace(number)
    turn = trace.span("turn", 0, turn_ms)
    at = 0.0
    for index, length in enumerate(llm_ms):
        step = trace.span("llm_call", at, length, parent=turn)
        usage: dict[str, Any] = {"gen_ai.provider.name": provider}
        if index < len(tokens):
            usage["gen_ai.usage.input_tokens"] = tokens[index][0]
            usage["gen_ai.usage.output_tokens"] = tokens[index][1]
        trace.span("chat", at, length, parent=step, **usage)
        at += length
    for length in tool_ms:
        trace.span("tool", at, length, parent=turn, **{"gen_ai.tool.name": "get_fact"})
        at += length
    return trace.records
