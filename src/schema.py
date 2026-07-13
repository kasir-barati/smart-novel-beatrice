"""
Root Strawberry schema.

Thin by design: import each module's resolvers and stitch them together into the top-level ``Query`` and ``Mutation`` types.

NOTE: modules never touch this file — they expose their resolvers and this file wires them.
"""

from __future__ import annotations

import strawberry

from src.modules.explain_word import WordExplanationType, explain_word
from src.modules.healthcheck import HealthCheck, healthcheck
from src.utils import GraphqlSpanRenameExtension


@strawberry.type
class Query:
    healthcheck: HealthCheck = strawberry.field(
        resolver=healthcheck,
        description="Healthcheck API which returns basic info about the service and if it is running.",
    )


@strawberry.type
class Mutation:
    explain_word: WordExplanationType = strawberry.mutation(
        resolver=explain_word,
        description=(
            "Return a structured explanation of a word as it is used in the given context. "
        ),
    )


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[GraphqlSpanRenameExtension],
)
