"""
Drop uninteresting noisy spans before they hit the OTLP exporter:

- IntrospectionQuery.
- Internal "/graphql http receive" and "/graphql http send".
"""

from __future__ import annotations

from opentelemetry.context import Context
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor


_EXCLUDE = {
    "graphql_operations": frozenset(
        {
            "healthcheck",
            "IntrospectionQuery",
        }
    ),
    "non_graphql_span_names": frozenset(
        {
            "GET /graphql",
            "HEAD /graphql",
            "OPTIONS /graphql",
        }
    ),
    "graphql_asgi_child_span_suffixes": (
        " /graphql http receive",
        " /graphql http send",
    ),
}


class ExcludeGraphQLOperationsSpanProcessor(SpanProcessor):
    def __init__(self, inner: SpanProcessor) -> None:
        self._inner = inner

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        """
        NOTE: we cannot decide to skip at start time — the GraphQL operation name is only set later, in the Strawberry `on_execute` extension. So we always let the inner processor observe the start and filter later on end.
        """

        self._inner.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        if span.name in _EXCLUDE["non_graphql_span_names"]:
            return

        if span.name.endswith(_EXCLUDE["graphql_asgi_child_span_suffixes"]):
            return

        attributes = span.attributes or {}
        operation_name = attributes.get("graphql.operation.name")
        if isinstance(operation_name, str) and operation_name in _EXCLUDE["graphql_operations"]:
            return

        self._inner.on_end(span)

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._inner.force_flush(timeout_millis)


__all__ = ["ExcludeGraphQLOperationsSpanProcessor"]
