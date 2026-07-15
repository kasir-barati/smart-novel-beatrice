from __future__ import annotations

import pytest

from src.modules.normalize_tts.exceptions import (
    LENGTH_DEVIATION_CODE,
    LengthDeviationError,
)


def test_length_deviation_exception_carries_code_and_lengths() -> None:
    exc = LengthDeviationError(
        input_length=120,
        output_length=42,
        max_deviation=0.3,
    )

    assert exc.code == LENGTH_DEVIATION_CODE
    assert exc.extensions is not None
    assert exc.extensions["code"] == LENGTH_DEVIATION_CODE
    assert exc.extensions["inputLength"] == 120
    assert exc.extensions["outputLength"] == 42
    assert exc.extensions["maxDeviation"] == pytest.approx(0.3)
    assert "120" in exc.message and "42" in exc.message
