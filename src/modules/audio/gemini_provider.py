"""
Gemini-TTS (Google Cloud Text-to-Speech) provider client.
"""

from __future__ import annotations

import base64
import uuid
from pathlib import Path

import httpx

from src.modules.audio.exceptions import TtsProviderError
from src.modules.audio.types import SynthesizedAudio, Voice
from src.utils import GeminiTtsSettings


PROVIDER_NAME = "gemini-tts"
_DEFAULT_LANGUAGE_CODE = "en-US"
_AUDIO_ENCODING = "MP3"


class GeminiTtsProvider:
    def __init__(
        self,
        settings: GeminiTtsSettings,
        output_dir: Path,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._output_dir = output_dir
        self._client = httpx.AsyncClient(
            base_url=settings.base_url,
            headers={"X-Goog-Api-Key": settings.api_key} if settings.api_key else {},
            timeout=settings.timeout_ms / 1000,
            transport=transport,
        )

    async def get_voices(self, *, language: str | None = None) -> list[Voice]:
        params = {"languageCode": language} if language is not None else {}
        response = await self._client.get("/v1/voices", params=params)
        if response.is_error:
            raise TtsProviderError(
                provider=PROVIDER_NAME,
                message=f"GET /v1/voices -> {response.status_code}",
                status_code=response.status_code,
            )

        payload = response.json()
        return [
            Voice(name=entry["name"], language_codes=entry.get("languageCodes", []))
            for entry in payload.get("voices", [])
        ]

    async def synthesize(self, *, text: str, voice: str) -> SynthesizedAudio:
        response = await self._client.post(
            "/v1/text:synthesize",
            json={
                "input": {"text": text},
                "voice": {"languageCode": _DEFAULT_LANGUAGE_CODE, "name": voice},
                "audioConfig": {"audioEncoding": _AUDIO_ENCODING},
            },
        )
        if response.is_error:
            raise TtsProviderError(
                provider=PROVIDER_NAME,
                message=f"POST /v1/text:synthesize -> {response.status_code}",
                status_code=response.status_code,
            )

        audio_bytes = base64.b64decode(response.json()["audioContent"])

        self._output_dir.mkdir(parents=True, exist_ok=True)
        file_path = self._output_dir / f"{uuid.uuid4()}.mp3"
        file_path.write_bytes(audio_bytes)

        return SynthesizedAudio(file_path=file_path)

    async def aclose(self) -> None:
        await self._client.aclose()
