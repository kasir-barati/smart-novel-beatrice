"""
OpenTelemetry + logging setup.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.utils.config import LoggingMode, Settings
from src.utils.graphql_span_rename import graphql_root_span_hook
from src.utils.span_filter import ExcludeGraphQLOperationsSpanProcessor


_LOG_RECORD_STANDARD_FIELDS: frozenset[str] = frozenset(
    logging.LogRecord(
        name="",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=None,
        exc_info=None,
    ).__dict__.keys()
    | {"message", "asctime"},
)
_configured: bool = False


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record on a single line"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Preserve any extras the caller attached via `extra={...}`.
        for key, value in record.__dict__.items():
            if key not in _LOG_RECORD_STANDARD_FIELDS:
                payload[key] = value

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def _configure_logging(settings: Settings) -> None:
    root = logging.getLogger()
    root.setLevel(settings.logging.level.value.upper())

    # Remove pre-existing handlers: logging setup takes ownership of the root logger when something else has already attached handlers first, such as pytest capture, uvicorn defaults, a prior basicConfig call, or an interactive reload.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    stream = logging.StreamHandler(stream=sys.stdout)

    if settings.logging.mode is LoggingMode.JSON:
        stream.setFormatter(JsonFormatter())
    else:
        stream.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    root.addHandler(stream)

    # Uvicorn ships its own coloured formatter — pipe its records through ours.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True


def _configure_tracing(settings: Settings, version: str) -> None:
    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": version,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=f"{settings.otel.exporter_otlp_endpoint}/v1/traces")
    span_processor = ExcludeGraphQLOperationsSpanProcessor(
        inner=BatchSpanProcessor(exporter),
    )
    provider.add_span_processor(span_processor)
    trace.set_tracer_provider(provider)

    # HTTPX must be instrumented BEFORE any AsyncClient is created (pydantic-ai creates one internally when the first agent is instantiated).
    HTTPXClientInstrumentor().instrument()


def setup_observability(settings: Settings, version: str) -> None:
    """
    Wire up logging + (optionally) OpenTelemetry tracing.

    Idempotent: calling `setup_observability` more than once is a no-op.
    """

    global _configured
    if _configured:
        return

    _configure_logging(settings)

    if settings.otel.enabled:
        _configure_tracing(settings, version)

    _configured = True


def instrument_fastapi(app: Any) -> None:
    """
    Attach the FastAPI OTel instrumentor to *app*.

    Kept separate from :func:`setup_observability` because the FastAPI app doesn't exist yet at logging-init time. When OTel is disabled this is a no-op — the instrumentor still runs but its spans get dropped by the ``NoOp`` tracer provider that OTel installs by default.
    """

    FastAPIInstrumentor.instrument_app(
        app,
        server_request_hook=graphql_root_span_hook,  # captures each server span into a `ContextVar` so `GraphqlSpanRenameExtension` can rename the root span from "POST /graphql" to the query/mutation name.
    )
