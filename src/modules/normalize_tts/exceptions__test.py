from __future__ import annotations

import pytest

from src.modules.normalize_tts.exceptions import (
    LENGTH_DEVIATION_CODE,
    LengthDeviationError,
)


def test_length_deviation_exception_carries_code_and_lengths() -> None:
    result = LengthDeviationError(
        input_length=120,
        output_length=42,
        max_deviation=0.3,
    )

    assert result.code == LENGTH_DEVIATION_CODE
    assert result.extensions is not None
    assert result.extensions["code"] == LENGTH_DEVIATION_CODE
    assert result.extensions["inputLength"] == 120
    assert result.extensions["outputLength"] == 42
    assert result.extensions["maxDeviation"] == pytest.approx(0.3)
    assert "120" in result.message and "42" in result.message
