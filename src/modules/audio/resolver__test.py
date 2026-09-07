from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

import httpx
import pytest
from strawberry.types import Info

from src.modules.audio import resolver
from src.modules.audio.exceptions import InstructNotSupportedError, InvalidVoiceError
from src.modules.audio.types import Voice
from src.utils import get_settings


@pytest.fixture(autouse=True)
def _clear_voices_cache() -> Iterator[None]:
    resolver._voices_cache = None
    yield
    resolver._voices_cache = None


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _FakeProvider:
    def __init__(self, voices: list[Voice]) -> None:
        self._voices = voices
        self.get_voices_call_count = 0
        self.closed = False

    async def get_voices(self, *, language: str | None = None) -> list[Voice]:
        self.get_voices_call_count += 1
        return self._voices

    async def synthesize(self, *, text: str, voice: str):  # pragma: no cover - unused here
        raise NotImplementedError

    async def aclose(self) -> None:
        self.closed = True


async def test_resolve_audio_voices_returns_provider_voice_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakeProvider([Voice(name="a"), Voice(name="b")])
    monkeypatch.setattr(resolver, "build_provider", lambda name, settings: fake_provider)

    result = await resolver.resolve_audio_voices()

    assert result == ["a", "b"]


async def test_resolve_audio_voices_closes_the_provider_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakeProvider([Voice(name="a")])
    monkeypatch.setattr(resolver, "build_provider", lambda name, settings: fake_provider)

    await resolver.resolve_audio_voices()

    assert fake_provider.closed is True


async def test_resolve_audio_voices_caches_across_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_provider = _FakeProvider([Voice(name="a")])
    monkeypatch.setattr(resolver, "build_provider", lambda name, settings: fake_provider)

    first = await resolver.resolve_audio_voices()
    second = await resolver.resolve_audio_voices()

    assert first == second
    assert fake_provider.get_voices_call_count == 1


def test_validate_text_length_accepts_text_within_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GENERATE_AUDIO__MAX_TEXT_LENGTH", "10")

    result = resolver._validate_text_length("short")

    assert result == "short"


def test_validate_text_length_rejects_text_over_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GENERATE_AUDIO__MAX_TEXT_LENGTH", "5")

    with pytest.raises(ValueError, match="at most 5 characters"):
        resolver._validate_text_length("too long")


class _FakeHttpxResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)  # type: ignore[arg-type]


class _FakeHttpxClient:
    def __init__(self, calls: list[dict[str, Any]], *, fail: bool) -> None:
        self._calls = calls
        self._fail = fail

    async def __aenter__(self) -> _FakeHttpxClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(
        self, url: str, *, json: dict[str, Any], headers: dict[str, str]
    ) -> _FakeHttpxResponse:
        self._calls.append({"url": url, "json": json, "headers": headers})
        if self._fail:
            raise httpx.ConnectError("connection refused")
        return _FakeHttpxResponse(200)


class _FakeInfo:
    def __init__(self, *, authorization: str | None = None) -> None:
        headers = {"authorization": authorization} if authorization is not None else {}
        self.context: dict[str, Any] = {
            "request": type("_FakeRequest", (), {"headers": headers})(),
            "response": type("_FakeResponse", (), {"status_code": None})(),
        }


def _fake_info(*, authorization: str | None = None) -> Info:
    """`generate_audio` only reads `.context`, so a duck-typed fake stands in for `Info`."""

    return cast(Info, _FakeInfo(authorization=authorization))


@pytest.fixture(autouse=True)
def _allow_generate_audio_test_settings(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GENERATE_AUDIO__CALLBACK__ALLOWED_HOSTS", "client.example.com")


async def test_generate_audio_rejects_a_voice_not_in_audio_voices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resolver, "resolve_audio_voices", _async_return(["known-voice"]))

    with pytest.raises(InvalidVoiceError):
        await resolver.generate_audio(
            text="hello",
            voice="unknown-voice",
            gen_upload_url="https://client.example.com/upload",
            status_callback_url="https://client.example.com/status",
            info=_fake_info(),
        )


async def test_generate_audio_publishes_and_responds_202(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resolver, "resolve_audio_voices", _async_return(["known-voice"]))
    published: list[dict[str, Any]] = []
    monkeypatch.setattr(resolver, "publish_generate_audio_job", _record_publish(published))
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        resolver.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls, fail=False)
    )
    info = _fake_info(authorization="Bearer secret")

    result = await resolver.generate_audio(
        text="hello",
        voice="known-voice",
        gen_upload_url="https://client.example.com/upload",
        status_callback_url="https://client.example.com/status",
        info=info,
    )

    assert result.job_id
    assert info.context["response"].status_code == 202
    assert len(published) == 1
    assert published[0]["body"]["text"] == "hello"
    assert published[0]["body"]["voice"] == "known-voice"
    assert published[0]["body"]["jobId"] == result.job_id
    assert published[0]["headers"]["authorization"] == "Bearer secret"
    assert "timestamp" in published[0]["headers"]
    assert len(calls) == 1
    assert calls[0]["json"] == {"status": "queued"}
    assert calls[0]["headers"] == {"authorization": "Bearer secret"}


async def test_generate_audio_omits_authorization_header_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resolver, "resolve_audio_voices", _async_return(["known-voice"]))
    published: list[dict[str, Any]] = []
    monkeypatch.setattr(resolver, "publish_generate_audio_job", _record_publish(published))
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        resolver.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls, fail=False)
    )

    await resolver.generate_audio(
        text="hello",
        voice="known-voice",
        gen_upload_url="https://client.example.com/upload",
        status_callback_url="https://client.example.com/status",
        info=_fake_info(),
    )

    assert "authorization" not in published[0]["headers"]
    assert calls[0]["headers"] == {}


async def test_generate_audio_rejects_instruct_when_provider_is_not_qwen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TTS__DEFAULT_PROVIDER", "gemini-tts")
    monkeypatch.setattr(resolver, "resolve_audio_voices", _async_return(["known-voice"]))

    with pytest.raises(InstructNotSupportedError):
        await resolver.generate_audio(
            text="hello",
            voice="known-voice",
            gen_upload_url="https://client.example.com/upload",
            status_callback_url="https://client.example.com/status",
            info=_fake_info(),
            instruct="speak in a whisper",
        )


async def test_generate_audio_includes_instruct_in_published_body_when_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resolver, "resolve_audio_voices", _async_return(["known-voice"]))
    published: list[dict[str, Any]] = []
    monkeypatch.setattr(resolver, "publish_generate_audio_job", _record_publish(published))
    monkeypatch.setattr(resolver.httpx, "AsyncClient", lambda **_: _FakeHttpxClient([], fail=False))

    await resolver.generate_audio(
        text="hello",
        voice="known-voice",
        gen_upload_url="https://client.example.com/upload",
        status_callback_url="https://client.example.com/status",
        info=_fake_info(),
        instruct="speak in a whisper",
    )

    assert published[0]["body"]["instruct"] == "speak in a whisper"


async def test_generate_audio_omits_instruct_from_published_body_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resolver, "resolve_audio_voices", _async_return(["known-voice"]))
    published: list[dict[str, Any]] = []
    monkeypatch.setattr(resolver, "publish_generate_audio_job", _record_publish(published))
    monkeypatch.setattr(resolver.httpx, "AsyncClient", lambda **_: _FakeHttpxClient([], fail=False))

    await resolver.generate_audio(
        text="hello",
        voice="known-voice",
        gen_upload_url="https://client.example.com/upload",
        status_callback_url="https://client.example.com/status",
        info=_fake_info(),
    )

    assert "instruct" not in published[0]["body"]


async def test_generate_audio_does_not_fail_when_queued_callback_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(resolver, "resolve_audio_voices", _async_return(["known-voice"]))
    published: list[dict[str, Any]] = []
    monkeypatch.setattr(resolver, "publish_generate_audio_job", _record_publish(published))
    monkeypatch.setattr(resolver.httpx, "AsyncClient", lambda **_: _FakeHttpxClient([], fail=True))
    info = _fake_info()

    result = await resolver.generate_audio(
        text="hello",
        voice="known-voice",
        gen_upload_url="https://client.example.com/upload",
        status_callback_url="https://client.example.com/status",
        info=info,
    )

    assert result.job_id
    assert info.context["response"].status_code == 202
    assert len(published) == 1


def _async_return(value: Any):
    async def _fn(*args: Any, **kwargs: Any) -> Any:
        return value

    return _fn


def _record_publish(sink: list[dict[str, Any]]):
    async def _fn(*, settings: Any, body: dict[str, Any], headers: dict[str, Any]) -> None:
        sink.append({"settings": settings, "body": body, "headers": headers})

    return _fn
