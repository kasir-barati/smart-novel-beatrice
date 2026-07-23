from __future__ import annotations

import logging
from typing import Annotated

import strawberry
from pydantic import StringConstraints

from src.modules.normalize_tts.agent import normalize_tts_via_agent
from src.modules.normalize_tts.exceptions import LengthDeviationError
from src.utils import LlmError, get_settings, spectaql_example


_logger = logging.getLogger(__name__)


def _length_deviation(input_len: int, output_len: int) -> float:
    if input_len == 0:
        return float("inf")

    return abs(output_len - input_len) / input_len


async def normalize_text_for_tts(
    text: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
        strawberry.argument(
            description=(
                "Raw text to be normalised for TTS — numbers, acronyms, symbols, and dates "
                "are rewritten into the form a speech engine can read aloud naturally. "
                "Must be 1..4000 characters."
            ),
            directives=[spectaql_example("Dr. Smith met with 3 clients at 9am on 12/03/2024.")],
        ),
    ],
) -> str:
    """Returns the LLM's TTS-normalised version of ``text``."""

    max_deviation = get_settings().normalize_tts.max_length_deviation

    try:
        result = await normalize_tts_via_agent(text=text)
    except Exception as exc:
        _logger.warning(
            "TTS normalization LLM call failed",
            extra={
                "input_length": len(text),
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
            exc_info=exc,
        )
        raise LlmError() from exc

    output = result.normalized_text
    deviation = _length_deviation(len(text), len(output))

    if deviation > max_deviation:
        raise LengthDeviationError(
            input_length=len(text),
            output_length=len(output),
            max_deviation=max_deviation,
        )

    return output
