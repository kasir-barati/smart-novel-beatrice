from __future__ import annotations

from src.modules.audio.exceptions import TTS_PROVIDER_ERROR_CODE, TtsProviderError
from src.modules.audio.provider import TtsProvider, TtsProviderName, build_provider
from src.modules.audio.types import SynthesizedAudio, Voice


__all__ = [
    "TTS_PROVIDER_ERROR_CODE",
    "SynthesizedAudio",
    "TtsProvider",
    "TtsProviderError",
    "TtsProviderName",
    "Voice",
    "build_provider",
]
