from __future__ import annotations

from src.utils import AppError


TTS_PROVIDER_ERROR_CODE = "TTS_PROVIDER_ERROR"


class TtsProviderError(AppError):
    """
    Raised when a TTS provider's voices/synthesize API call fails.

    Carries `status_code` (when known) so `src.modules.audio.retry.decide_retry` can
    classify the failure the same way it classifies an `httpx.HTTPStatusError`.
    """

    def __init__(self, *, provider: str, message: str, status_code: int | None = None) -> None:
        extensions: dict[str, object] = {"provider": provider}
        if status_code is not None:
            extensions["statusCode"] = status_code

        super().__init__(
            code=TTS_PROVIDER_ERROR_CODE,
            message=f"{provider}: {message}",
            extensions=extensions,
        )
        self.status_code = status_code


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


INSTRUCT_NOT_SUPPORTED_ERROR_CODE = "INSTRUCT_NOT_SUPPORTED"


class InstructNotSupportedError(AppError):
    """
    Raised when `generateAudio` is called with `instruct` set but the configured
    provider has no style/tone control (only Qwen3-TTS supports `instruct` today).
    """

    def __init__(self, *, provider: str) -> None:
        super().__init__(
            code=INSTRUCT_NOT_SUPPORTED_ERROR_CODE,
            message=f"'{provider}' does not support the 'instruct' argument.",
            extensions={"provider": provider},
        )
