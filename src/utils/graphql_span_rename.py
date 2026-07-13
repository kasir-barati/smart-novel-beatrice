"""
Rename the incoming HTTP OpenTelemetry span to the GraphQL operation.

Failure mode: if parsing / validation fail, ``on_execute`` never fires — the span keeps its ``POST /graphql`` name.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from graphql import OperationDefinitionNode
from graphql.language import FieldNode
from opentelemetry import trace
from strawberry.extensions import SchemaExtension


if TYPE_CHECKING:
    from opentelemetry.trace import Span


_root_span: ContextVar[Span | None] = ContextVar("graphql_span_rename__root_span", default=None)
"""
Populated per-request by :func:`graphql_root_span_hook`.
"""


def graphql_root_span_hook(span: Span, scope: dict[str, Any]) -> None:
    """
    Capture *span* as the current request's root span for later renaming.

    Only fires for HTTP scopes; other ASGI scopes (``lifespan``, ``websocket``, …) are ignored.
    """

    if scope.get("type") != "http":
        return

    _root_span.set(span)


def _get_operation_label(
    operation_name: str | None,
    operation: OperationDefinitionNode,
) -> str:
    """Return a human-readable label for the operation.

    - mutation CreateNovel { … } → CreateNovel
    - mutation { explain(…) } → explain

    For multi anonymous operations only the first root is captured — acceptable tradeoff.
    """

    if operation_name:
        return operation_name

    first_selection = (
        operation.selection_set.selections[0] if operation.selection_set.selections else None
    )

    if isinstance(first_selection, FieldNode):
        return first_selection.name.value

    return "<anonymous>"


class GraphqlSpanRenameExtension(SchemaExtension):
    """Rename the active OTel span to ``<operationLabel> <operationType>``"""

    def on_execute(self) -> Iterator[None]:
        """
        Fires *after* parse + validate (so ``graphql_document`` is populated) but *before* resolvers run.
        """
        ctx = self.execution_context
        document = ctx.graphql_document

        if document is not None:
            operation = next(
                (
                    definition
                    for definition in document.definitions
                    if isinstance(definition, OperationDefinitionNode)
                ),
                None,
            )
            if operation is not None:
                span = _root_span.get() or trace.get_current_span()
                operation_type = operation.operation.value
                operation_label = _get_operation_label(ctx.operation_name, operation)

                span.update_name(f"{operation_label} {operation_type}")
                span.set_attribute("graphql.operation.type", operation_type)
                span.set_attribute("graphql.operation.name", operation_label)

        yield


__all__ = ["GraphqlSpanRenameExtension", "graphql_root_span_hook"]
