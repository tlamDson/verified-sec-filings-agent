"""Where spans go, from the environment.

`PHOENIX_COLLECTOR_ENDPOINT` (Phoenix's base URL, e.g. http://localhost:6006) sends spans
to Phoenix over OTLP HTTP, at `/v1/traces`. `SEC_AGENT_TRACE_FILE` appends them to a JSONL
file as well, for `sec-agent traces table`. With neither, nothing is installed and every
span is a no-op. Both exporters batch in the background: a slow or absent Phoenix never
holds up a question.
"""

from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from pydantic import BaseModel, ConfigDict

from sec_agent.observability.conventions import AGENT
from sec_agent.observability.span_file import JsonlSpanExporter

PHOENIX_ENDPOINT_VAR = "PHOENIX_COLLECTOR_ENDPOINT"
TRACE_FILE_VAR = "SEC_AGENT_TRACE_FILE"
OTLP_TRACES_PATH = "/v1/traces"

OtlpExporterFactory = Callable[[str], SpanExporter]


class TracingConfigError(ValueError):
    pass


class TraceSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    otlp_endpoint: str | None
    """The OTLP HTTP traces URL, or None for no export to Phoenix."""
    file: Path | None


def trace_settings_from_env(environ: Mapping[str, str]) -> TraceSettings:
    endpoint = environ.get(PHOENIX_ENDPOINT_VAR, "").strip()
    file = environ.get(TRACE_FILE_VAR, "").strip()
    return TraceSettings(
        otlp_endpoint=_traces_url(endpoint) if endpoint else None,
        file=Path(file) if file else None,
    )


def build_tracer_provider(
    settings: TraceSettings, *, otlp_exporter: OtlpExporterFactory | None = None
) -> TracerProvider | None:
    """A provider exporting where `settings` say; None when they name nowhere."""
    if settings.otlp_endpoint is None and settings.file is None:
        return None
    provider = TracerProvider(resource=Resource.create({"service.name": AGENT}))
    if settings.otlp_endpoint is not None:
        make = otlp_exporter or _otlp_http
        provider.add_span_processor(BatchSpanProcessor(make(settings.otlp_endpoint)))
    if settings.file is not None:
        provider.add_span_processor(BatchSpanProcessor(JsonlSpanExporter(settings.file)))
    return provider


@contextmanager
def tracing(environ: Mapping[str, str]) -> Generator[TracerProvider | None]:
    """Install the provider the environment asks for, for the life of the process, and
    flush it on the way out. Raises `TracingConfigError` for a malformed setting."""
    provider = build_tracer_provider(trace_settings_from_env(environ))
    if provider is None:
        yield None
        return
    trace.set_tracer_provider(provider)
    try:
        yield provider
    finally:
        provider.shutdown()


def _otlp_http(endpoint: str) -> SpanExporter:
    return OTLPSpanExporter(endpoint=endpoint)


def _traces_url(value: str) -> str:
    """The OTLP traces URL for a Phoenix base URL. The value is never echoed in an error:
    a URL with credentials in it is refused, and so not repeated."""
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise TracingConfigError(f"{PHOENIX_ENDPOINT_VAR} must be an http or https URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise TracingConfigError(
            f"{PHOENIX_ENDPOINT_VAR} must be a plain URL: no credentials, query or fragment"
        )
    base = value.rstrip("/")
    return base if base.endswith(OTLP_TRACES_PATH) else base + OTLP_TRACES_PATH
