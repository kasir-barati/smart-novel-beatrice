from __future__ import annotations

from src.utils import AppError


LENGTH_DEVIATION_CODE = "LENGTH_DEVIATION"


class LengthDeviationError(AppError):
    """
    Raised when the LLM output length strays too far from the input.
    """

    def __init__(
        self,
        *,
        input_length: int,
        output_length: int,
        max_deviation: float,
    ) -> None:
        super().__init__(
            code=LENGTH_DEVIATION_CODE,
            message=(
                f"TTS normalization output length ({output_length}) deviates "
                f"more than {max_deviation:.0%} from input length ({input_length})."
            ),
            extensions={
                "inputLength": input_length,
                "outputLength": output_length,
                "maxDeviation": max_deviation,
            },
        )
