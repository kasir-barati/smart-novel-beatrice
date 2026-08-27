"""
Resolvers for the audio module's GraphQL surface.
"""

from __future__ import annotations

import asyncio

from src.modules.audio.provider import build_provider
from src.utils import get_settings


_voices_cache: list[str] | None = None
_voices_cache_lock = asyncio.Lock()


async def resolve_audio_voices() -> list[str]:
    """
    Return the configured provider's voice names, fetched once and cached for the
    lifetime of the process — see `Tts.default_provider` for which provider backs this.
    """

    global _voices_cache

    if _voices_cache is not None:
        return _voices_cache

    async with _voices_cache_lock:
        if _voices_cache is None:
            settings = get_settings()
            provider = build_provider(settings.tts.default_provider, settings)
            try:
                voices = await provider.get_voices()
            finally:
                await provider.aclose()
            _voices_cache = [voice.name for voice in voices]

    return _voices_cache
