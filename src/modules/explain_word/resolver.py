from __future__ import annotations

import logging
from typing import Annotated

import strawberry

from src.modules.explain_word.agent import explain_word_via_agent
from src.modules.explain_word.types import WordExplanationType
from src.utils import LlmError, NonEmptyTrimmedString, spectaql_example


_logger = logging.getLogger(__name__)


async def explain_word(
    word: Annotated[
        NonEmptyTrimmedString,
        strawberry.argument(
            description="The single word to explain.",
            directives=[spectaql_example("impulse")],
        ),
    ],
    context: Annotated[
        NonEmptyTrimmedString,
        strawberry.argument(
            description=(
                "The sentence or paragraph the word appears in — used to disambiguate its meaning."
            ),
            directives=[
                spectaql_example("She acted on impulse and booked a flight home the same night.")
            ],
        ),
    ],
) -> WordExplanationType:
    """explainWord resolver for the GraphQL API"""

    try:
        result = await explain_word_via_agent(word=word, context=context)
    except Exception as exc:
        _logger.warning(
            "explainWord LLM call failed",
            extra={
                "word": word,
                "context_length": len(context),
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
            exc_info=exc,
        )

        raise LlmError() from exc

    return WordExplanationType.from_pydantic(result)
