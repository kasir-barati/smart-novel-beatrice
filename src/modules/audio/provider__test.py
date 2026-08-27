from __future__ import annotations

from src.modules.audio.gemini_provider import GeminiTtsProvider
from src.modules.audio.provider import TtsProviderName, build_provider
from src.modules.audio.qwen_provider import Qwen3TtsProvider
from src.utils import get_settings


def test_build_provider_returns_qwen_for_qwen_name() -> None:
    provider = build_provider(TtsProviderName.QWEN3_TTS, get_settings())

    assert isinstance(provider, Qwen3TtsProvider)


def test_build_provider_returns_gemini_for_gemini_name() -> None:
    provider = build_provider(TtsProviderName.GEMINI_TTS, get_settings())

    assert isinstance(provider, GeminiTtsProvider)
