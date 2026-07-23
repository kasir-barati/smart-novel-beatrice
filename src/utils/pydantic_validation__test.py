# pyright: reportOptionalSubscript=false, reportOptionalMemberAccess=false

from __future__ import annotations

from typing import Annotated

import strawberry
from pydantic import EmailStr, StringConstraints

from src.utils.pydantic_validation import apply_pydantic_validation


# ---------------------------------------------------------------------------
# Scalar argument validation
# ---------------------------------------------------------------------------


@strawberry.type
class _Query:
    ping: str = strawberry.field(default="pong")


@strawberry.type
class _ScalarMutation:
    @strawberry.mutation
    def echo(
        self,
        text: Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=5),
        ],
    ) -> str:
        return text


apply_pydantic_validation(_Query, _ScalarMutation)
_scalar_schema = strawberry.Schema(query=_Query, mutation=_ScalarMutation)


async def test_scalar_valid_input_is_accepted() -> None:
    result = await _scalar_schema.execute(
        "mutation ($t: String!) { echo(text: $t) }",
        variable_values={"t": "hi"},
    )

    assert result.errors is None
    assert result.data == {"echo": "hi"}


async def test_scalar_whitespace_is_stripped() -> None:
    result = await _scalar_schema.execute(
        "mutation ($t: String!) { echo(text: $t) }",
        variable_values={"t": "  hi  "},
    )

    assert result.errors is None
    assert result.data == {"echo": "hi"}


async def test_scalar_input_longer_than_max_length_is_rejected() -> None:
    result = await _scalar_schema.execute(
        "mutation ($t: String!) { echo(text: $t) }",
        variable_values={"t": "way too long"},
    )

    assert result.errors is not None
    message = result.errors[0].message
    assert "text" in message
    assert "at most 5 characters" in message


async def test_scalar_whitespace_only_input_is_rejected() -> None:
    result = await _scalar_schema.execute(
        "mutation ($t: String!) { echo(text: $t) }",
        variable_values={"t": "   "},
    )

    assert result.errors is not None
    assert "at least 1 character" in result.errors[0].message


async def test_scalar_schema_exposes_plain_string() -> None:
    sdl = _scalar_schema.as_str()

    assert "text: String!" in sdl
    assert "NonEmptyTrimmedString" not in sdl


# ---------------------------------------------------------------------------
# Nested @strawberry.input validation
# ---------------------------------------------------------------------------


@strawberry.input
class _UserInfoInput:
    name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    ]
    email: Annotated[str, EmailStr]
    password: Annotated[str, StringConstraints(min_length=8, max_length=128)]


@strawberry.type
class _UserOutput:
    name: str
    email: str


@strawberry.type
class _InputMutation:
    @strawberry.mutation
    def create_user(self, user: _UserInfoInput) -> _UserOutput:
        return _UserOutput(name=user.name, email=user.email)


apply_pydantic_validation(_Query, _InputMutation)
_input_schema = strawberry.Schema(query=_Query, mutation=_InputMutation)


_CREATE_USER = """
mutation ($user: Userinfoinput!) {
    createUser(user: $user) {
        name
        email
    }
}
"""


async def test_input_valid_data_is_accepted_and_trimmed() -> None:
    result = await _input_schema.execute(
        _CREATE_USER,
        variable_values={
            "user": {
                "name": "   Ada Lovelace   ",
                "email": "ada@example.com",
                "password": "s3cret-password",
            }
        },
    )

    assert result.errors is None
    assert result.data["createUser"] == {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
    }


async def test_input_invalid_email_is_rejected() -> None:
    result = await _input_schema.execute(
        _CREATE_USER,
        variable_values={
            "user": {
                "name": "Ada",
                "email": "not-an-email",
                "password": "s3cret-password",
            }
        },
    )

    assert result.errors is not None
    assert "email" in result.errors[0].message.lower()


async def test_input_short_password_is_rejected() -> None:
    result = await _input_schema.execute(
        _CREATE_USER,
        variable_values={
            "user": {
                "name": "Ada",
                "email": "ada@example.com",
                "password": "short",
            }
        },
    )

    assert result.errors is not None
    assert "password" in result.errors[0].message.lower()


async def test_input_empty_name_is_rejected() -> None:
    result = await _input_schema.execute(
        _CREATE_USER,
        variable_values={
            "user": {
                "name": "   ",
                "email": "ada@example.com",
                "password": "s3cret-password",
            }
        },
    )

    assert result.errors is not None
    assert "name" in result.errors[0].message.lower()


async def test_apply_pydantic_validation_is_idempotent() -> None:
    @strawberry.type
    class _Q:
        ping: str = strawberry.field(default="pong")

    @strawberry.type
    class _M:
        @strawberry.mutation
        def echo(
            self,
            text: Annotated[str, StringConstraints(min_length=1, max_length=5)],
        ) -> str:
            return text

    apply_pydantic_validation(_Q, _M)
    apply_pydantic_validation(_Q, _M)
    schema = strawberry.Schema(query=_Q, mutation=_M)

    result = await schema.execute(
        "mutation ($t: String!) { echo(text: $t) }",
        variable_values={"t": "hi"},
    )

    assert result.errors is None
    assert result.data == {"echo": "hi"}


# ---------------------------------------------------------------------------
# Passthrough behavior for unconstrained scalar arguments
# ---------------------------------------------------------------------------


@strawberry.type
class _PlainMutation:
    @strawberry.mutation
    def echo(self, text: str) -> str:
        return text


apply_pydantic_validation(_Query, _PlainMutation)
_plain_schema = strawberry.Schema(query=_Query, mutation=_PlainMutation)


async def test_argument_without_metadata_is_passthrough() -> None:
    result = await _plain_schema.execute(
        "mutation ($t: String!) { echo(text: $t) }",
        variable_values={"t": "anything goes, no constraints at all"},
    )

    assert result.errors is None
    assert result.data == {"echo": "anything goes, no constraints at all"}


# ---------------------------------------------------------------------------
# Nested @strawberry.input validation -- Recurse into inner input types
# ---------------------------------------------------------------------------


@strawberry.input
class _Character:
    canonical_name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    ]
    pronouns: (
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=32),
        ]
        | None
    ) = None


@strawberry.input
class _NovelContext:
    protagonist: _Character
    characters: list[_Character] = strawberry.field(default_factory=list)


@strawberry.type
class _NestedMutation:
    @strawberry.mutation
    def normalize(
        self,
        text: Annotated[str, StringConstraints(min_length=1, max_length=100)],
        context: _NovelContext | None = None,
    ) -> str:
        if context is None:
            return text

        return (
            f"{text}"
            f"|protagonist={context.protagonist.canonical_name}"
            f"|pronouns={context.protagonist.pronouns}"
            f"|chars={[c.canonical_name for c in context.characters]}"
        )


apply_pydantic_validation(_Query, _NestedMutation)
_nested_schema = strawberry.Schema(query=_Query, mutation=_NestedMutation)


_NESTED_MUTATION = """
mutation ($t: String!, $ctx: Novelcontext) {
    normalize(text: $t, context: $ctx)
}
"""


async def test_nested_input_field_over_max_length_is_rejected() -> None:
    result = await _nested_schema.execute(
        _NESTED_MUTATION,
        variable_values={
            "t": "hello",
            "ctx": {
                "protagonist": {
                    # NOTE: 👇 Strawberry will auto convert this to snake_case.
                    "canonicalName": "A" * 100,
                    "pronouns": "she/her",
                },
                "characters": [],
            },
        },
    )

    assert result.errors is not None
    message = result.errors[0].message.lower()
    assert "canonicalname" in message or "canonical_name" in message
    assert "at most 64 characters" in message


async def test_nested_input_empty_field_is_rejected() -> None:
    result = await _nested_schema.execute(
        _NESTED_MUTATION,
        variable_values={
            "t": "hello",
            "ctx": {
                "protagonist": {
                    # NOTE: 👇 Strawberry will auto convert this to snake_case.
                    "canonicalName": "   ",
                    "pronouns": "she/her",
                },
                "characters": [],
            },
        },
    )

    assert result.errors is not None
    message = result.errors[0].message.lower()
    assert "canonicalname" in message or "canonical_name" in message
    assert "at least 1 character" in message


async def test_nested_input_field_is_trimmed() -> None:
    result = await _nested_schema.execute(
        _NESTED_MUTATION,
        variable_values={
            "t": "hello",
            "ctx": {
                "protagonist": {
                    # NOTE: 👇 Strawberry will auto convert this to snake_case.
                    "canonicalName": "   Alice   ",
                    "pronouns": "  she/her  ",
                },
                "characters": [],
            },
        },
    )

    assert result.errors is None
    data = result.data["normalize"]
    assert "protagonist=Alice" in data
    assert "pronouns=she/her" in data


async def test_nested_input_inside_list_over_max_length_is_rejected() -> None:
    result = await _nested_schema.execute(
        _NESTED_MUTATION,
        variable_values={
            "t": "hello",
            "ctx": {
                "protagonist": {
                    # NOTE: 👇 Strawberry will auto convert this to snake_case.
                    "canonicalName": "Alice"
                },
                "characters": [
                    # NOTE: 👇 Strawberry will auto convert this to snake_case.
                    {"canonicalName": "Bob"},
                    {"canonicalName": "B" * 100},
                ],
            },
        },
    )

    assert result.errors is not None
    message = result.errors[0].message.lower()
    assert "at most 64 characters" in message
    # The error should ideally point at the offending index (e.g. "characters.1").
    assert "characters" in message


async def test_nested_input_inside_list_is_trimmed() -> None:
    result = await _nested_schema.execute(
        _NESTED_MUTATION,
        variable_values={
            "t": "hello",
            "ctx": {
                # NOTE: 👇 Strawberry will auto convert this to snake_case.
                "protagonist": {"canonicalName": "Alice"},
                "characters": [{"canonicalName": "  Bob  "}],
            },
        },
    )

    assert result.errors is None
    assert "chars=['Bob']" in result.data["normalize"]


async def test_nested_input_valid_data_still_reaches_resolver_today() -> None:
    result = await _nested_schema.execute(
        _NESTED_MUTATION,
        variable_values={
            "t": "hello",
            "ctx": {
                # NOTE: 👇 Strawberry will auto convert this to snake_case.
                "protagonist": {"canonicalName": "Alice", "pronouns": "she/her"},
                "characters": [{"canonicalName": "Bob"}],
            },
        },
    )

    assert result.errors is None
    data = result.data["normalize"]
    assert "protagonist=Alice" in data
    assert "chars=['Bob']" in data
