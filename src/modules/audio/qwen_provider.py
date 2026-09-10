"""
Qwen3-TTS provider client, talking to Alibaba Cloud DashScope's native REST API
directly. Voices are static config (`QwenTtsSettings.voices`) — see `QwenTtsSettings`
for why. English-only for now: DashScope's request body takes a `language_type`
field, hardcoded here to `"English"`.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx

from src.modules.audio.exceptions import TtsProviderError
from src.modules.audio.types import SynthesizedAudio, Voice
from src.utils import QwenTtsSettings


PROVIDER_NAME = "qwen3-tts"
_LANGUAGE_TYPE = "English"


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

        return [Voice(name=name) for name in self._settings.voices_list]

    async def synthesize(
        self, *, text: str, voice: str, instruct: str | None = None
    ) -> SynthesizedAudio:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        file_path = self._output_dir / f"{uuid.uuid4()}.mp3"

        body: dict[str, object] = {
            "model": self._settings.model,
            "input": {"text": text, "voice": voice, "language_type": _LANGUAGE_TYPE},
        }
        if instruct is not None:
            body["instructions"] = instruct

        response = await self._client.post(self._settings.synthesize_path, json=body)
        if response.is_error:
            raise TtsProviderError(
                provider=PROVIDER_NAME,
                message=f"POST {self._settings.synthesize_path} -> {response.status_code}",
                status_code=response.status_code,
            )

        audio_url = response.json()["output"]["audio"]["url"]

        async with self._client.stream("GET", audio_url) as download:
            if download.is_error:
                await download.aread()
                raise TtsProviderError(
                    provider=PROVIDER_NAME,
                    message=f"GET {audio_url} -> {download.status_code}",
                    status_code=download.status_code,
                )

            with file_path.open("wb") as fh:
                async for chunk in download.aiter_bytes():
                    fh.write(chunk)

        return SynthesizedAudio(file_path=file_path)

    async def aclose(self) -> None:
        await self._client.aclose()
