from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from src.modules.audio.exceptions import TtsProviderError
from src.modules.audio.qwen_provider import Qwen3TtsProvider
from src.utils import QwenTtsSettings


def _settings() -> QwenTtsSettings:
    return QwenTtsSettings(api_key="test-key")


def _provider(tmp_path: Path, handler) -> Qwen3TtsProvider:
    return Qwen3TtsProvider(_settings(), tmp_path, transport=httpx.MockTransport(handler))


async def test_get_voices_returns_names(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/voices"
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"voices": [{"name": "qwen-female-1"}]})

    provider = _provider(tmp_path, handler)

    voices = await provider.get_voices()

    assert [v.name for v in voices] == ["qwen-female-1"]
    assert voices[0].language_codes == []


async def test_get_voices_rejects_language_filter() -> None:
    provider = Qwen3TtsProvider(_settings(), Path("/tmp"))

    with pytest.raises(ValueError, match="does not support filtering"):
        await provider.get_voices(language="en-US")


async def test_get_voices_raises_on_error_response(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    provider = _provider(tmp_path, handler)

    with pytest.raises(TtsProviderError):
        await provider.get_voices()


async def test_synthesize_writes_raw_response_bytes_to_output_dir(tmp_path: Path) -> None:
    audio_bytes = b"raw-audio-bytes"

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body == {"model": "Qwen/Qwen3-TTS", "input": "hello", "voice": "qwen-female-1"}
        return httpx.Response(200, content=audio_bytes)

    provider = _provider(tmp_path, handler)

    result = await provider.synthesize(text="hello", voice="qwen-female-1")

    assert result.file_path.parent == tmp_path
    assert result.file_path.read_bytes() == audio_bytes


async def test_synthesize_raises_on_error_response(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": "bad input"})

    provider = _provider(tmp_path, handler)

    with pytest.raises(TtsProviderError):
        await provider.synthesize(text="hi", voice="nonexistent")


async def test_synthesize_forwards_instruct_when_given(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body == {
            "model": "Qwen/Qwen3-TTS",
            "input": "hello",
            "voice": "qwen-female-1",
            "instruct": "speak in a whisper",
        }
        return httpx.Response(200, content=b"raw-audio-bytes")

    provider = _provider(tmp_path, handler)

    await provider.synthesize(text="hello", voice="qwen-female-1", instruct="speak in a whisper")


async def test_synthesize_omits_instruct_when_not_given(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "instruct" not in body
        return httpx.Response(200, content=b"raw-audio-bytes")

    provider = _provider(tmp_path, handler)

    await provider.synthesize(text="hello", voice="qwen-female-1")
