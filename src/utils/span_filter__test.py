from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor

from src.utils import ExcludeGraphQLOperationsSpanProcessor


def _make_span(operation_name: str | None, name: str = "POST /graphql") -> ReadableSpan:
    """
    Build a minimal :class:`ReadableSpan` stub with a name + one attribute.

    We only touch ``.attributes`` and ``.name`` in the processor, so a plain object with those attributes is enough — spinning up a real ``TracerProvider`` just to build one span would slow every test by an order of magnitude.
    """

    attributes: dict[str, object] = {}

    if operation_name is not None:
        attributes["graphql.operation.name"] = operation_name

    span = MagicMock(spec=ReadableSpan)
    span.attributes = attributes
    span.name = name

    return cast(ReadableSpan, span)


def test_forwards_span_when_operation_name_not_excluded() -> None:
    inner = MagicMock(spec=SpanProcessor)
    processor = ExcludeGraphQLOperationsSpanProcessor(inner=inner)

    processor.on_end(_make_span("explainWord"))

    inner.on_end.assert_called_once()


@pytest.mark.parametrize(
    "operation_name",
    [
        "healthcheck",
        "IntrospectionQuery",
    ],
)
def test_drops_excluded_query_operation(operation_name: str) -> None:
    inner = MagicMock(spec=SpanProcessor)
    processor = ExcludeGraphQLOperationsSpanProcessor(inner=inner)

    processor.on_end(_make_span(operation_name))

    inner.on_end.assert_not_called()


def test_forwards_span_without_operation_name() -> None:
    """Non-GraphQL spans (HTTPX, FastAPI middleware) have no operation name."""

    inner = MagicMock(spec=SpanProcessor)
    processor = ExcludeGraphQLOperationsSpanProcessor(inner=inner)

    processor.on_end(_make_span(None, name="HTTP GET http://ollama:11434/v1/chat"))

    inner.on_end.assert_called_once()


def test_drops_non_post_graphql_spans() -> None:
    inner = MagicMock(spec=SpanProcessor)
    processor = ExcludeGraphQLOperationsSpanProcessor(inner=inner)

    processor.on_end(_make_span(None, name="GET /graphql"))
    processor.on_end(_make_span(None, name="HEAD /graphql"))
    processor.on_end(_make_span(None, name="OPTIONS /graphql"))

    inner.on_end.assert_not_called()


def test_drops_graphql_asgi_child_event_spans() -> None:
    inner = MagicMock(spec=SpanProcessor)
    processor = ExcludeGraphQLOperationsSpanProcessor(inner=inner)

    processor.on_end(_make_span(None, name="POST /graphql http receive"))
    processor.on_end(_make_span(None, name="POST /graphql http send"))
    processor.on_end(_make_span(None, name="GET /graphql http send"))

    inner.on_end.assert_not_called()


def test_post_graphql_span_is_kept() -> None:
    inner = MagicMock(spec=SpanProcessor)
    processor = ExcludeGraphQLOperationsSpanProcessor(inner=inner)

    processor.on_end(_make_span("explainWord", name="POST /graphql"))

    inner.on_end.assert_called_once()


def test_lifecycle_methods_delegate_to_inner() -> None:
    inner = MagicMock(spec=SpanProcessor)
    inner.force_flush.return_value = True
    processor = ExcludeGraphQLOperationsSpanProcessor(inner=inner)

    processor.on_start(cast(Span, MagicMock()), None)
    processor.shutdown()
    result = processor.force_flush(5_000)

    inner.on_start.assert_called_once()
    inner.shutdown.assert_called_once()
    inner.force_flush.assert_called_once_with(5_000)
    assert result is True
