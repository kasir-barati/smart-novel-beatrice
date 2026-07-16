"""
SpectaQL schema directive for enriching the API docs.
"""

from __future__ import annotations

import json
from typing import Any

import strawberry
from strawberry.schema_directive import Location


@strawberry.input(description="A single (key, value) option accepted by @spectaql.")
class SpectaqlOption:
    key: str
    value: str


@strawberry.schema_directive(
    locations=[
        Location.OBJECT,
        Location.FIELD_DEFINITION,
        Location.ARGUMENT_DEFINITION,
        Location.SCALAR,
        Location.INPUT_OBJECT,
        Location.INPUT_FIELD_DEFINITION,
        Location.INTERFACE,
        Location.UNION,
        Location.ENUM,
        Location.ENUM_VALUE,
    ],
    name="spectaql",
    description="Metadata for SpectaQL docs (examples, undocumented flags, …).",
)
class Spectaql:
    options: list[SpectaqlOption]


def spectaql_example(value: Any) -> Spectaql:
    """
    Attach a single example value to a field/arg/type.

    ``value`` can be any JSON-serialisable Python value (str, int, bool, list,
    dict). SpectaQL parses the emitted string back based on the ``example`` key.

    Example
    -------
    >>> import strawberry
    >>> @strawberry.type
    ... class Service:
    ...     version: str = strawberry.field(
    ...         description="Service version.",
    ...         directives=[spectaql_example("1.0.1")],
    ...     )

    Emitted in the final GQL schema as::

        type Service {
          version: String! @spectaql(options: [{key: "example", value: "\"1.0.1\""}])
        }
    """
    return Spectaql(options=[SpectaqlOption(key="example", value=json.dumps(value))])


def spectaql_examples(values: list[Any]) -> Spectaql:
    """
    Attach a list of example values; SpectaQL picks one per build.

    Example
    -------
    >>> import strawberry
    >>> @strawberry.type
    ... class Book:
    ...     genre: str = strawberry.field(
    ...         description="Book genre.",
    ...         directives=[spectaql_examples(["fantasy", "romance", "sci-fi"])],
    ...     )

    Emitted in the final GQL schema as::

        type Book {
          genre: String! @spectaql(
            options: [
              {key: "examples", value: "[\"fantasy\", \"romance\", \"sci-fi\"]"}
            ]
          )
        }
    """
    return Spectaql(options=[SpectaqlOption(key="examples", value=json.dumps(values))])
