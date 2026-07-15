from __future__ import annotations

from typing import Any, NewType

import strawberry


NonEmptyTrimmedString = NewType("NonEmptyTrimmedString", str)
"""
Non-empty, whitespace-trimmed string.
"""


def _parse_non_empty_trimmed_string(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("NonEmptyTrimmedString must be a string")

    stripped = value.strip()

    if not stripped:
        raise ValueError("NonEmptyTrimmedString must not be empty or whitespace-only")

    return stripped


_NON_EMPTY_TRIMMED_STRING = strawberry.scalar(
    name="NonEmptyTrimmedString",
    description=(
        "String scalar that trims leading/trailing whitespace and rejects "
        "empty or whitespace-only values."
    ),
    serialize=lambda value: value,
    parse_value=_parse_non_empty_trimmed_string,
)


SCALAR_MAP: dict[object, Any] = {
    NonEmptyTrimmedString: _NON_EMPTY_TRIMMED_STRING,
}
"""
The full scalar map to hand to :class:`StrawberryConfig` when building the schema.
"""
