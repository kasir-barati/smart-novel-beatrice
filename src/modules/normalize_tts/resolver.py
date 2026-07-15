from __future__ import annotations

import logging

from src.modules.normalize_tts.agent import normalize_tts_via_agent
from src.modules.normalize_tts.exceptions import LengthDeviationError
from src.utils import LlmError, NonEmptyTrimmedString, get_settings


_logger = logging.getLogger(__name__)


def _length_deviation(input_len: int, output_len: int) -> float:
    if input_len == 0:
        return float("inf")

    return abs(output_len - input_len) / input_len


async def normalize_text_for_tts(text: NonEmptyTrimmedString) -> str:
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
