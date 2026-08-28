"""
Qwen3-TTS provider client, called through a third-party OpenAI-compatible inference
host (DeepInfra by default — see `QwenTtsSettings` for why the paths are configurable).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx

from src.modules.audio.exceptions import TtsProviderError
from src.modules.audio.types import SynthesizedAudio, Voice
from src.utils import QwenTtsSettings


PROVIDER_NAME = "qwen3-tts"


class Qwen3TtsProvider:
    def __init__(
        self,
        settings: QwenTtsSettings,
        output_dir: Path,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._output_dir = output_dir
        self._client = httpx.AsyncClient(
            base_url=settings.base_url,
            headers={"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {},
            timeout=settings.timeout_ms / 1000,
            transport=transport,
        )

    async def get_voices(self, *, language: str | None = None) -> list[Voice]:
        if language is not None:
            raise ValueError("Qwen3-TTS does not support filtering voices by language.")

        response = await self._client.get(self._settings.voices_path)
        if response.is_error:
            raise TtsProviderError(
                provider=PROVIDER_NAME,
                message=f"GET {self._settings.voices_path} -> {response.status_code}",
                status_code=response.status_code,
            )

        payload = response.json()
        return [Voice(name=entry["name"]) for entry in payload.get("voices", [])]

    async def synthesize(self, *, text: str, voice: str) -> SynthesizedAudio:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        file_path = self._output_dir / f"{uuid.uuid4()}.mp3"

        async with self._client.stream(
            "POST",
            self._settings.synthesize_path,
            json={"model": self._settings.model, "input": text, "voice": voice},
        ) as response:
            if response.is_error:
                await response.aread()
                raise TtsProviderError(
                    provider=PROVIDER_NAME,
                    message=f"POST {self._settings.synthesize_path} -> {response.status_code}",
                    status_code=response.status_code,
                )

            with file_path.open("wb") as fh:
                async for chunk in response.aiter_bytes():
                    fh.write(chunk)

        return SynthesizedAudio(file_path=file_path)

    async def aclose(self) -> None:
        await self._client.aclose()
