from __future__ import annotations

from src.utils import AppError


TTS_PROVIDER_ERROR_CODE = "TTS_PROVIDER_ERROR"


class TtsProviderError(AppError):
    """
    Raised when a TTS provider's voices/synthesize API call fails.
    """

    def __init__(self, *, provider: str, message: str) -> None:
        super().__init__(
            code=TTS_PROVIDER_ERROR_CODE,
            message=f"{provider}: {message}",
            extensions={"provider": provider},
        )
