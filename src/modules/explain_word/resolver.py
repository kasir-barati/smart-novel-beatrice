from __future__ import annotations

import logging

from src.modules.explain_word.agent import explain_word_via_agent
from src.modules.explain_word.types import WordExplanationType
from src.utils import LlmError, NonEmptyTrimmedString


_logger = logging.getLogger(__name__)


async def explain_word(
    word: NonEmptyTrimmedString, context: NonEmptyTrimmedString
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
