from __future__ import annotations

from src.modules.audio.exceptions import (
    INVALID_VOICE_ERROR_CODE,
    TTS_PROVIDER_ERROR_CODE,
    InvalidVoiceError,
    TtsProviderError,
)
from src.modules.audio.provider import TtsProvider, TtsProviderName, build_provider
from src.modules.audio.resolver import GenerateAudioResult, generate_audio, resolve_audio_voices
from src.modules.audio.types import SynthesizedAudio, Voice


__all__ = [
    "INVALID_VOICE_ERROR_CODE",
    "TTS_PROVIDER_ERROR_CODE",
    "GenerateAudioResult",
    "InvalidVoiceError",
    "SynthesizedAudio",
    "TtsProvider",
    "TtsProviderError",
    "TtsProviderName",
    "Voice",
    "build_provider",
    "generate_audio",
    "resolve_audio_voices",
]
