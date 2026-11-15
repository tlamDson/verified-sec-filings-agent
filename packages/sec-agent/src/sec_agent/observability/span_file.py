"""Spans as JSON lines: one finished span per line, appended by `JsonlSpanExporter`.

The file is what `sec-agent traces table` reads, so the L1 numbers come from a file kept
with the run rather than from a query against Phoenix. Each process should write its own
file: lines from two processes appending at once are not guaranteed to stay whole.
"""

import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, Self, cast

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import StatusCode
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

AttributeValue = str | bool | int | float | list[str] | list[bool] | list[int] | list[float]
SpanStatus = Literal["unset", "ok", "error"]
_STATUS: dict[StatusCode, SpanStatus] = {
    StatusCode.UNSET: "unset",
    StatusCode.OK: "ok",
    StatusCode.ERROR: "error",
}


class SpanFileError(ValueError):
    pass


class SpanRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    span_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    parent_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")
    name: str
    start_ns: int = Field(ge=0)
    end_ns: int = Field(ge=0)
    status: SpanStatus
    attributes: dict[str, AttributeValue] = Field(default_factory=dict[str, AttributeValue])

    @model_validator(mode="after")
    def _ends_after_start(self) -> Self:
        if self.end_ns < self.start_ns:
            raise ValueError("the span ends before it starts")
        return self

    @property
    def duration_ms(self) -> float:
        return (self.end_ns - self.start_ns) / 1_000_000


def span_record(span: ReadableSpan) -> SpanRecord | None:
    """The record of a finished span; None for a span without context or end time."""
    context = span.context
    if context is None or span.start_time is None or span.end_time is None:
        return None
    attributes: dict[str, AttributeValue] = {}
    for key, value in (span.attributes or {}).items():
        if (kept := _attribute(value)) is not None:
            attributes[key] = kept
    return SpanRecord(
        trace_id=f"{context.trace_id:032x}",
        span_id=f"{context.span_id:016x}",
        parent_id=f"{span.parent.span_id:016x}" if span.parent is not None else None,
        name=span.name,
        start_ns=span.start_time,
        end_ns=span.end_time,
        status=_STATUS[span.status.status_code],
        attributes=attributes,
    )


def _attribute(value: object) -> AttributeValue | None:
    """A scalar, or a list of one scalar type; None for anything else (no span here has
    one: bytes, maps and mixed lists are left out)."""
    if isinstance(value, str | bool | int | float):
        return value
    if not isinstance(value, list | tuple):
        return None
    items: list[object] = list(cast(Sequence[object], value))
    strings = [i for i in items if isinstance(i, str)]
    if len(strings) == len(items):
        return strings
    flags = [i for i in items if isinstance(i, bool)]
    if len(flags) == len(items):
        return flags
    whole = [i for i in items if isinstance(i, int) and not isinstance(i, bool)]
    if len(whole) == len(items):
        return whole
    real = [i for i in items if isinstance(i, float)]
    return real if len(real) == len(items) else None


class JsonlSpanExporter(SpanExporter):
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        records = [r for r in (span_record(s) for s in spans) if r is not None]
        text = "".join(r.model_dump_json() + "\n" for r in records)
        try:
            with self._lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(text)
        except OSError:
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


def read_spans(path: Path) -> list[SpanRecord]:
    """Every record of the file, in order; blank lines are skipped."""
    try:
        lines = path.read_text("utf-8").splitlines()
    except FileNotFoundError:
        raise SpanFileError(f"no span file at {path}") from None
    records: list[SpanRecord] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append(SpanRecord.model_validate_json(line))
        except ValidationError:
            raise SpanFileError(f"{path}: line {number} is not a span record") from None
    return records
