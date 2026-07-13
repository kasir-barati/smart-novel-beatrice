from __future__ import annotations

from collections.abc import Iterator
from contextvars import ContextVar
from typing import TYPE_CHECKING

import pytest
import strawberry
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.utils.graphql_span_rename import (
    GraphqlSpanRenameExtension,
    graphql_root_span_hook,
)


if TYPE_CHECKING:
    from opentelemetry.trace import Span


@strawberry.type
class _Query:
    @strawberry.field
    def ping(self) -> str:
        return "pong"


@strawberry.type
class _Mutation:
    @strawberry.mutation
    def bump(self) -> int:
        return 42


_schema = strawberry.Schema(
    query=_Query,
    mutation=_Mutation,
    extensions=[GraphqlSpanRenameExtension],
)


@pytest.fixture
def tracer_setup() -> Iterator[tuple[trace.Tracer, InMemorySpanExporter]]:
    """
    Isolate each test with its own tracer provider + in-memory exporter.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    previous_provider = trace.get_tracer_provider()
    trace.set_tracer_provider(provider)
    tracer = provider.get_tracer(__name__)
    try:
        yield tracer, exporter
    finally:
        trace.set_tracer_provider(previous_provider)
        exporter.clear()


@pytest.fixture
def isolated_root_span(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Swap the module-level ``_root_span`` ContextVar for a fresh one per test.

    In production the ContextVar is scoped to each ASGI request's asyncio task and cleaned up implicitly by task teardown.
    """

    fresh: ContextVar[Span | None] = ContextVar(
        "graphql_span_rename__root_span__test",
        default=None,
    )
    monkeypatch.setattr("src.utils.graphql_span_rename._root_span", fresh)


async def test_renames_span_for_named_query(
    tracer_setup: tuple[trace.Tracer, InMemorySpanExporter],
) -> None:
    tracer, exporter = tracer_setup

    with tracer.start_as_current_span("POST /graphql"):
        result = await _schema.execute("query GetPing { ping }")

    assert result.errors is None
    span = exporter.get_finished_spans()[0]
    assert span.name == "GetPing query"
    assert span.attributes is not None
    assert span.attributes["graphql.operation.type"] == "query"
    assert span.attributes["graphql.operation.name"] == "GetPing"


async def test_renames_span_for_named_mutation(
    tracer_setup: tuple[trace.Tracer, InMemorySpanExporter],
) -> None:
    tracer, exporter = tracer_setup

    with tracer.start_as_current_span("POST /graphql"):
        result = await _schema.execute("mutation DoBump { bump }")

    assert result.errors is None
    span = exporter.get_finished_spans()[0]
    assert span.name == "DoBump mutation"
    assert span.attributes is not None
    assert span.attributes["graphql.operation.type"] == "mutation"
    assert span.attributes["graphql.operation.name"] == "DoBump"


async def test_anonymous_operation_falls_back_to_root_field(
    tracer_setup: tuple[trace.Tracer, InMemorySpanExporter],
) -> None:
    tracer, exporter = tracer_setup

    with tracer.start_as_current_span("POST /graphql"):
        result = await _schema.execute("{ ping }")

    assert result.errors is None
    span = exporter.get_finished_spans()[0]
    assert span.name == "ping query"
    assert span.attributes is not None
    assert span.attributes["graphql.operation.name"] == "ping"


async def test_parse_error_leaves_span_untouched(
    tracer_setup: tuple[trace.Tracer, InMemorySpanExporter],
) -> None:
    tracer, exporter = tracer_setup

    with tracer.start_as_current_span("POST /graphql"):
        result = await _schema.execute("query { this is not valid")

    assert result.errors is not None
    span = exporter.get_finished_spans()[0]
    assert span.name == "POST /graphql"
    assert span.attributes is not None
    assert "graphql.operation.name" not in span.attributes


async def test_no_active_recording_span_is_safe(
    tracer_setup: tuple[trace.Tracer, InMemorySpanExporter],
) -> None:
    _, exporter = tracer_setup

    result = await _schema.execute("query GetPing { ping }")

    assert result.errors is None
    # No span was started, so nothing was exported — the extension is a no-op.
    assert exporter.get_finished_spans() == ()


async def test_hook_captured_span_is_renamed_not_current_child(
    tracer_setup: tuple[trace.Tracer, InMemorySpanExporter],
    isolated_root_span: None,
) -> None:
    tracer, exporter = tracer_setup

    with tracer.start_as_current_span("POST /graphql") as server_span:
        graphql_root_span_hook(server_span, {"type": "http"})
        with tracer.start_as_current_span("POST /graphql http receive"):
            result = await _schema.execute("query GetPing { ping }")

    assert result.errors is None
    spans_by_name = {span.name: span for span in exporter.get_finished_spans()}
    assert "POST /graphql http receive" in spans_by_name
    assert "GetPing query" in spans_by_name
    server = spans_by_name["GetPing query"]
    assert server.attributes is not None
    assert server.attributes["graphql.operation.name"] == "GetPing"


@pytest.mark.parametrize("scope_type", ["lifespan", "websocket"])
async def test_hook_ignores_non_http_scopes(
    tracer_setup: tuple[trace.Tracer, InMemorySpanExporter],
    isolated_root_span: None,
    scope_type: str,
) -> None:
    tracer, exporter = tracer_setup

    with tracer.start_as_current_span("POST /graphql") as server_span:
        graphql_root_span_hook(server_span, {"type": scope_type})
        with tracer.start_as_current_span("child"):
            await _schema.execute("query GetPing { ping }")

    span_names = {span.name for span in exporter.get_finished_spans()}
    assert "POST /graphql" in span_names
