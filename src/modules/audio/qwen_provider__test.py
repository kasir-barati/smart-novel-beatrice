from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from src.modules.audio.exceptions import TtsProviderError
from src.modules.audio.qwen_provider import Qwen3TtsProvider
from src.utils import QwenTtsSettings


_AUDIO_URL = "https://dashscope-intl.aliyuncs.com/audio/output.wav"


def _settings() -> QwenTtsSettings:
    return QwenTtsSettings(api_key="test-key", voices="qwen-female-1,qwen-male-1")


def _provider(tmp_path: Path, handler) -> Qwen3TtsProvider:
    return Qwen3TtsProvider(_settings(), tmp_path, transport=httpx.MockTransport(handler))


def _synthesize_handler(audio_bytes: bytes):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            assert str(request.url) == _AUDIO_URL
            return httpx.Response(200, content=audio_bytes)

        return httpx.Response(200, json={"output": {"audio": {"url": _AUDIO_URL}}})

    return handler


async def test_get_voices_returns_names_from_settings() -> None:
    provider = Qwen3TtsProvider(_settings(), Path("/tmp"))

    voices = await provider.get_voices()

    assert [v.name for v in voices] == ["qwen-female-1", "qwen-male-1"]
    assert voices[0].language_codes == []


async def test_get_voices_rejects_language_filter() -> None:
    provider = Qwen3TtsProvider(_settings(), Path("/tmp"))

    with pytest.raises(ValueError, match="does not support filtering"):
        await provider.get_voices(language="en-US")


async def test_synthesize_posts_dashscope_shaped_body(tmp_path: Path) -> None:
    seen_body: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            seen_body.update(json.loads(request.content))
            return httpx.Response(200, json={"output": {"audio": {"url": _AUDIO_URL}}})
        return httpx.Response(200, content=b"audio-bytes")

    provider = _provider(tmp_path, handler)

    await provider.synthesize(text="hello", voice="qwen-female-1")

    assert seen_body == {
        "model": "qwen3-tts-instruct-flash",
        "input": {"text": "hello", "voice": "qwen-female-1", "language_type": "English"},
    }


async def test_synthesize_downloads_audio_url_to_output_dir(tmp_path: Path) -> None:
    audio_bytes = b"downloaded-audio-bytes"
    provider = _provider(tmp_path, _synthesize_handler(audio_bytes))

    result = await provider.synthesize(text="hello", voice="qwen-female-1")

    assert result.file_path.parent == tmp_path
    assert result.file_path.read_bytes() == audio_bytes


async def test_synthesize_raises_on_error_response_from_initial_post(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": "bad input"})

    provider = _provider(tmp_path, handler)

    with pytest.raises(TtsProviderError):
        await provider.synthesize(text="hi", voice="nonexistent")


async def test_synthesize_raises_on_error_response_from_audio_download(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"output": {"audio": {"url": _AUDIO_URL}}})
        return httpx.Response(500, content=b"gone")

    provider = _provider(tmp_path, handler)

    with pytest.raises(TtsProviderError):
        await provider.synthesize(text="hi", voice="qwen-female-1")


async def test_synthesize_forwards_instruct_as_instructions_when_given(tmp_path: Path) -> None:
    seen_body: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            seen_body.update(json.loads(request.content))
            return httpx.Response(200, json={"output": {"audio": {"url": _AUDIO_URL}}})
        return httpx.Response(200, content=b"audio-bytes")

    provider = _provider(tmp_path, handler)

    await provider.synthesize(text="hello", voice="qwen-female-1", instruct="speak in a whisper")

    assert seen_body["instructions"] == "speak in a whisper"
    assert "instruct" not in seen_body


async def test_synthesize_omits_instructions_when_not_given(tmp_path: Path) -> None:
    seen_body: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            seen_body.update(json.loads(request.content))
            return httpx.Response(200, json={"output": {"audio": {"url": _AUDIO_URL}}})
        return httpx.Response(200, content=b"audio-bytes")

    provider = _provider(tmp_path, handler)

    await provider.synthesize(text="hello", voice="qwen-female-1")

    assert "instructions" not in seen_body
