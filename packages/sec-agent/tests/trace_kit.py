"""An in-memory tracer for the tracing tests. Pytest puts this directory on sys.path.

Spans stay in memory (`InMemorySpanExporter`): nothing is exported, nothing leaves the
process.
"""

from collections.abc import Sequence

from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Tracer


class Traces:
    def __init__(self) -> None:
        self._exporter = InMemorySpanExporter()
        self._provider = TracerProvider()
        self._provider.add_span_processor(SimpleSpanProcessor(self._exporter))

    @property
    def tracer(self) -> Tracer:
        return self._provider.get_tracer("tests")

    def spans(self) -> Sequence[ReadableSpan]:
        """Finished spans, in the order they ended."""
        return self._exporter.get_finished_spans()

    def step(self, step: str) -> list[ReadableSpan]:
        return [s for s in self.spans() if (s.attributes or {}).get("sec_agent.step") == step]

    def one(self, step: str) -> ReadableSpan:
        (span,) = self.step(step)
        return span


def parent_id(span: ReadableSpan) -> int | None:
    return span.parent.span_id if span.parent is not None else None


def span_id(span: ReadableSpan) -> int:
    context = span.context
    assert context is not None
    return context.span_id


def attrs(span: ReadableSpan) -> dict[str, object]:
    return dict(span.attributes or {})
