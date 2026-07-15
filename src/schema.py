"""
Root Strawberry schema.

Thin by design: import each module's resolvers and stitch them together into the top-level ``Query`` and ``Mutation`` types.

NOTE: modules never touch this file — they expose their resolvers and this file wires them.
"""

from __future__ import annotations

import strawberry
from strawberry.schema.config import StrawberryConfig

from src.modules.explain_word import WordExplanationType, explain_word
from src.modules.healthcheck import HealthCheck, healthcheck
from src.modules.normalize_tts import normalize_text_for_tts
from src.utils import SCALAR_MAP, GraphqlSpanRenameExtension


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
    normalize_text_for_tts: str = strawberry.mutation(
        resolver=normalize_text_for_tts,
        description="Return an LLM-normalised version of the given text suitable for TTS.",
    )


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[GraphqlSpanRenameExtension],
    config=StrawberryConfig(scalar_map=SCALAR_MAP),
)
