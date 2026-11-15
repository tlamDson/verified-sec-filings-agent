"""Where spans go, from the environment: Phoenix over OTLP HTTP, a JSONL file, or nowhere.

No test exports over the network: the OTLP exporter is replaced by a recording factory.
"""

from collections.abc import Sequence
from pathlib import Path

import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from sec_agent.observability.setup import (
    TraceSettings,
    TracingConfigError,
    build_tracer_provider,
    trace_settings_from_env,
    tracing,
)
from sec_agent.observability.span_file import read_spans


class _Recording(SpanExporter):
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self.spans: list[ReadableSpan] = []

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS


def test_nothing_configured_means_no_provider() -> None:
    settings = trace_settings_from_env({})
    assert settings == TraceSettings(otlp_endpoint=None, file=None)
    assert build_tracer_provider(settings) is None


@pytest.mark.parametrize(
    "base",
    [
        "http://localhost:6006",
        "http://localhost:6006/",
        "http://localhost:6006/v1/traces",
    ],
)
def test_the_phoenix_endpoint_is_its_otlp_http_traces_path(base: str) -> None:
    settings = trace_settings_from_env({"PHOENIX_COLLECTOR_ENDPOINT": base})
    assert settings.otlp_endpoint == "http://localhost:6006/v1/traces"


@pytest.mark.parametrize(
    "value", ["localhost:6006", "ftp://localhost:6006", "http://user:secret@localhost:6006"]
)
def test_a_bad_endpoint_is_refused_without_echoing_it(value: str) -> None:
    with pytest.raises(TracingConfigError, match="PHOENIX_COLLECTOR_ENDPOINT") as raised:
        trace_settings_from_env({"PHOENIX_COLLECTOR_ENDPOINT": value})
    assert "secret" not in str(raised.value)


def test_a_blank_setting_counts_as_unset() -> None:
    env = {"PHOENIX_COLLECTOR_ENDPOINT": "  ", "SEC_AGENT_TRACE_FILE": ""}
    assert trace_settings_from_env(env) == TraceSettings(otlp_endpoint=None, file=None)


def test_spans_go_to_the_otlp_exporter_under_the_service_name() -> None:
    made: list[_Recording] = []

    def factory(endpoint: str) -> SpanExporter:
        made.append(_Recording(endpoint))
        return made[-1]

    settings = TraceSettings(otlp_endpoint="http://localhost:6006/v1/traces", file=None)
    provider = build_tracer_provider(settings, otlp_exporter=factory)
    assert provider is not None
    assert provider.resource.attributes["service.name"] == "sec-agent"
    with provider.get_tracer("tests").start_as_current_span("one"):
        pass
    provider.shutdown()
    (exporter,) = made
    assert exporter.endpoint == "http://localhost:6006/v1/traces"
    assert [s.name for s in exporter.spans] == ["one"]


def test_spans_go_to_the_file_when_one_is_named(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    settings = trace_settings_from_env({"SEC_AGENT_TRACE_FILE": str(path)})
    assert settings.file == path
    provider = build_tracer_provider(settings)
    assert provider is not None
    with provider.get_tracer("tests").start_as_current_span("one"):
        pass
    provider.shutdown()
    assert [r.name for r in read_spans(path)] == ["one"]


def test_tracing_without_settings_installs_nothing() -> None:
    with tracing({}) as provider:
        assert provider is None
