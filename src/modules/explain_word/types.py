from __future__ import annotations

import strawberry
from pydantic import BaseModel, Field, field_validator

from src.utils import spectaql_example


def _dedupe_and_cap(values: list[str]) -> list[str]:
    """
    Case-insensitively deduplicate ``values``, then cap the result at 5.
    """

    seen: set[str] = set()
    cleaned: list[str] = []

    for value in values:
        key = value.strip().lower()

        if not key or key in seen:
            continue

        seen.add(key)
        cleaned.append(value.strip())

    return cleaned[:5]


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

    @field_validator("synonyms", "antonyms", mode="after")
    @classmethod
    def _normalize_word_list(cls, values: list[str]) -> list[str]:
        return _dedupe_and_cap(values)


@strawberry.experimental.pydantic.type(
    model=WordExplanation,
    description="Structured explanation of one word as it is used in a specific context.",
)
class WordExplanationType:
    """GraphQL projection of :class:`WordExplanation`."""

    meaning: strawberry.auto = strawberry.field(
        description="Concise dictionary-style definition of the word as used in context.",
        directives=[spectaql_example("A sudden strong urge to do something impulsive.")],
    )
    simplified_explanation: strawberry.auto = strawberry.field(
        description="Same idea expressed for a younger or non-native reader.",
        directives=[
            spectaql_example(
                "A quick feeling that makes you want to do something without thinking."
            )
        ],
    )
    synonyms: strawberry.auto = strawberry.field(
        description="Up to five words meaning roughly the same thing.",
        directives=[spectaql_example(["urge", "whim", "impulse", "instinct"])],
    )
    antonyms: strawberry.auto = strawberry.field(
        description="Up to five words meaning roughly the opposite.",
        directives=[spectaql_example(["hesitation", "deliberation", "restraint"])],
    )
