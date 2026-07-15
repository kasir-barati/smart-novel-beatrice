from __future__ import annotations

import pytest
import strawberry
from strawberry.schema.config import StrawberryConfig

from src.utils.graphql_scalars import SCALAR_MAP, NonEmptyTrimmedString


@strawberry.type
class _Query:
    ping: str = strawberry.field(default="pong")


@strawberry.type
class _Mutation:
    @strawberry.mutation
    def echo(self, text: NonEmptyTrimmedString) -> str:
        return text


_schema = strawberry.Schema(
    query=_Query,
    mutation=_Mutation,
    config=StrawberryConfig(scalar_map=SCALAR_MAP),
)


@pytest.mark.parametrize(
    ("raw_input", "expected"),
    [
        ("hello", "hello"),
        ("  hello  ", "hello"),
        ("\thi\n", "hi"),
    ],
)
async def test_scalar_trims_whitespace(raw_input: str, expected: str) -> None:
    result = await _schema.execute(
        "mutation N($t: NonEmptyTrimmedString!) { echo(text: $t) }",
        variable_values={"t": raw_input},
    )

    assert result.errors is None
    assert result.data == {"echo": expected}


@pytest.mark.parametrize("bad_input", ["", " ", "\n\t "])
async def test_scalar_rejects_empty_or_whitespace(bad_input: str) -> None:
    result = await _schema.execute(
        "mutation N($t: NonEmptyTrimmedString!) { echo(text: $t) }",
        variable_values={"t": bad_input},
    )

    assert result.data is None
    assert result.errors is not None
    assert any("NonEmptyTrimmedString" in str(e.message) for e in result.errors)
