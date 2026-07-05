"""
Root Strawberry schema.

Thin by design: import each module's resolvers and stitch them together into the top-level ``Query`` and (later) ``Mutation`` types.

NOTE: modules never touch this file — they expose their resolvers and this file wires them.

As new endpoints land the pattern is:

.. code-block:: python

    from src.modules.explain_word import explain_word

    @strawberry.type
    class Mutation:
        explain_word: WordExplanation = strawberry.mutation(resolver=explain_word)
"""

from __future__ import annotations

import strawberry

from src.modules.healthcheck import HealthCheck, healthcheck
from src.utils import GraphqlSpanRenameExtension


@strawberry.type
class Query:
    healthcheck: HealthCheck = strawberry.field(
        resolver=healthcheck,
        description="Healthcheck API which returns basic info about the service and if it is running.",
    )


schema = strawberry.Schema(
    query=Query,
    extensions=[GraphqlSpanRenameExtension],
)
