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


INVALID_VOICE_ERROR_CODE = "INVALID_VOICE"


class InvalidVoiceError(AppError):
    """
    Raised when `generateAudio` is called with a voice name the configured provider
    doesn't offer (per `audioVoices`).
    """

    def __init__(self, *, voice: str) -> None:
        super().__init__(
            code=INVALID_VOICE_ERROR_CODE,
            message=f"'{voice}' is not a voice the configured provider accepts.",
            extensions={"voice": voice},
        )
