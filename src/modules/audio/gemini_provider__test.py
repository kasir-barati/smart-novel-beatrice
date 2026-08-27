from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from src.modules.audio.exceptions import TtsProviderError
from src.modules.audio.gemini_provider import GeminiTtsProvider
from src.utils import GeminiTtsSettings


def _settings() -> GeminiTtsSettings:
    return GeminiTtsSettings(api_key="test-key")


def _provider(tmp_path: Path, handler) -> GeminiTtsProvider:
    return GeminiTtsProvider(_settings(), tmp_path, transport=httpx.MockTransport(handler))


async def test_get_voices_returns_name_and_language_codes(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Goog-Api-Key"] == "test-key"
        return httpx.Response(
            200,
            json={
                "voices": [
                    {"name": "en-US-Standard-A", "languageCodes": ["en-US"]},
                    {"name": "es-419-Standard-B", "languageCodes": ["es-419"]},
                ]
            },
        )

    provider = _provider(tmp_path, handler)

    voices = await provider.get_voices()

    assert [v.name for v in voices] == ["en-US-Standard-A", "es-419-Standard-B"]
    assert voices[0].language_codes == ["en-US"]


async def test_get_voices_filters_by_language_query_param(tmp_path: Path) -> None:
    seen_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(request.url.params)
        return httpx.Response(200, json={"voices": []})

    provider = _provider(tmp_path, handler)

    await provider.get_voices(language="es-419")

    assert seen_params == {"languageCode": "es-419"}


async def test_get_voices_raises_on_error_response(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    provider = _provider(tmp_path, handler)

    with pytest.raises(TtsProviderError):
        await provider.get_voices()


async def test_synthesize_writes_decoded_audio_to_output_dir(tmp_path: Path) -> None:
    audio_bytes = b"not-really-mp3-bytes"

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["input"]["text"] == "hello world"
        assert body["voice"]["name"] == "en-US-Standard-A"
        return httpx.Response(200, json={"audioContent": base64.b64encode(audio_bytes).decode()})

    provider = _provider(tmp_path, handler)

    result = await provider.synthesize(text="hello world", voice="en-US-Standard-A")

    assert result.file_path.parent == tmp_path
    assert result.file_path.read_bytes() == audio_bytes


async def test_synthesize_raises_on_error_response(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad voice"})

    provider = _provider(tmp_path, handler)

    with pytest.raises(TtsProviderError):
        await provider.synthesize(text="hi", voice="nonexistent")
