"""
Shared GraphQL exceptions.
"""

from __future__ import annotations

from typing import Any

from graphql import GraphQLError


LLM_ERROR_CODE = "LLM_ERROR"


class AppError(GraphQLError):
    """
    Base class for every domain error raised through the GraphQL surface.
    """

    def __init__(
        self,
        *,
        code: str,
        message: str,
        extensions: dict[str, Any] | None = None,
    ) -> None:
        merged: dict[str, Any] = {"code": code}
        if extensions:
            merged.update(extensions)
        super().__init__(message, extensions=merged)
        self.code = code


class LlmError(AppError):
    """
    Raised when an upstream LLM call fails for any reason.
    """

    def __init__(self, message: str = "LLM call failed.") -> None:
        super().__init__(code=LLM_ERROR_CODE, message=message)
