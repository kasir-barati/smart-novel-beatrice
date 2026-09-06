"""
Unified interface Beatrice talks to regardless of which TTS provider is configured.

Only English is supported for voice discovery today: Gemini-TTS's `/v1/voices` can be
filtered by BCP-47 language code, but Qwen3-TTS's third-party inference APIs expose no
per-voice language metadata, so `language` is rejected outright for that provider.
"""

from __future__ import annotations

from typing import Protocol

from src.modules.audio.gemini_provider import GeminiTtsProvider
from src.modules.audio.qwen_provider import Qwen3TtsProvider
from src.modules.audio.types import SynthesizedAudio, Voice
from src.utils import Settings, TtsProviderName


class TtsProvider(Protocol):
    async def get_voices(self, *, language: str | None = None) -> list[Voice]:
        """
        List every voice this provider offers.

        :param language: BCP-47 language tag to filter by (e.g. "en-US"). Only
            supported by providers that expose per-voice language metadata;
            passing this to a provider that doesn't raises ``ValueError``.
        """
        ...

    async def synthesize(
        self, *, text: str, voice: str, instruct: str | None = None
    ) -> SynthesizedAudio:
        """
        Generate speech audio for `text` using `voice`, and store it to disk.

        :param instruct: Natural-language style/tone/emotion guidance. Only Qwen3-TTS
            supports this; passing it to a provider that doesn't raises
            `InstructNotSupportedError`.
        """
        ...

    async def aclose(self) -> None:
        """Release the underlying HTTP client."""
        ...


def build_provider(name: TtsProviderName, settings: Settings) -> TtsProvider:
    """Construct the configured provider client for `name`."""

    output_dir = settings.tts.output_dir

    if name is TtsProviderName.QWEN3_TTS:
        return Qwen3TtsProvider(settings.tts.qwen, output_dir)
    return GeminiTtsProvider(settings.tts.gemini, output_dir)
