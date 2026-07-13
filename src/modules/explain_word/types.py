from __future__ import annotations

import strawberry
from pydantic import BaseModel, Field


class WordExplanation(BaseModel):
    """Structured explanation of one word as it is used in a specific context."""

    meaning: str = Field(
        description="Concise dictionary-style definition of the word as used in context.",
    )
    simplified_explanation: str = Field(
        description="Same idea expressed for a younger or non-native reader.",
    )
    synonyms: list[str] = Field(
        default_factory=list,
        description="Up to five words meaning roughly the same thing.",
    )
    antonyms: list[str] = Field(
        default_factory=list,
        description="Up to five words meaning roughly the opposite.",
    )


@strawberry.experimental.pydantic.type(
    model=WordExplanation,
    all_fields=True,
    description="Structured explanation of one word as it is used in a specific context.",
)
class WordExplanationType:
    """GraphQL projection of :class:`WordExplanation`."""
