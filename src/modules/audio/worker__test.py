from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.modules.audio import worker as worker_module
from src.modules.audio.types import GenerateAudioJob, SynthesizedAudio
from src.modules.audio.worker import (
    GENERATING_CALL_PERCENT,
    GENERATING_STARTED_PERCENT,
    handle_message,
    report_progress,
    synthesize_job,
)
from src.utils import get_settings


@pytest.fixture(autouse=True)
def _allow_client_example_com(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[None]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GENERATE_AUDIO__CALLBACK__ALLOWED_HOSTS", "client.example.com")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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


async def test_report_progress_posts_status_and_percent(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        worker_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls, fail=False)
    )

    await report_progress(
        "http://client.example.com/status",
        status="generating",
        percent=12,
        authorization="Bearer secret",
        job_id="job-1",
    )

    assert calls == [
        {
            "url": "http://client.example.com/status",
            "json": {"status": "generating", "percent": 12},
            "headers": {"authorization": "Bearer secret"},
        }
    ]


async def test_report_progress_does_not_raise_on_callback_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        worker_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient([], fail=True)
    )

    await report_progress(
        "http://client.example.com/status",
        status="generating",
        percent=0,
        authorization=None,
        job_id="job-1",
    )


async def test_report_progress_refuses_a_host_not_on_the_allow_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The URL was already validated once by generateAudio, but this process only has the
    queue message to go on — it must not trust that validation carried across the hop.
    """

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        worker_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls, fail=False)
    )

    await report_progress(
        "https://evil.example.com/status",
        status="generating",
        percent=0,
        authorization=None,
        job_id="job-1",
    )

    assert calls == []


class _FakeProvider:
    def __init__(self, result: SynthesizedAudio) -> None:
        self._result = result
        self.synthesize_calls: list[dict[str, Any]] = []
        self.closed = False

    async def get_voices(self, *, language: str | None = None):  # pragma: no cover - unused here
        raise NotImplementedError

    async def synthesize(self, *, text: str, voice: str) -> SynthesizedAudio:
        self.synthesize_calls.append({"text": text, "voice": voice})
        return self._result

    async def aclose(self) -> None:
        self.closed = True


def _job(**overrides: str) -> GenerateAudioJob:
    base = {
        "jobId": "job-1",
        "text": "hello",
        "voice": "qwen-voice-a",
        "genUploadUrl": "https://client.example.com/upload",
        "statusCallbackUrl": "https://client.example.com/status",
    }
    base.update(overrides)
    return GenerateAudioJob.model_validate(base)


async def test_synthesize_job_reports_progress_then_calls_the_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    result = SynthesizedAudio(file_path=tmp_path / "out.mp3")
    fake_provider = _FakeProvider(result)
    monkeypatch.setattr(worker_module, "build_provider", lambda name, settings: fake_provider)
    progress_calls: list[dict[str, Any]] = []

    async def _fake_report_progress(url: str, *, status: str, percent: int, **kwargs: Any) -> None:
        progress_calls.append({"url": url, "status": status, "percent": percent})

    monkeypatch.setattr(worker_module, "report_progress", _fake_report_progress)

    job = _job()
    returned = await synthesize_job(job, authorization=None)

    assert returned is result
    assert fake_provider.synthesize_calls == [{"text": "hello", "voice": "qwen-voice-a"}]
    assert fake_provider.closed is True
    assert [c["percent"] for c in progress_calls] == [
        GENERATING_STARTED_PERCENT,
        GENERATING_CALL_PERCENT,
    ]
    assert all(c["status"] == "generating" for c in progress_calls)


async def test_synthesize_job_closes_the_provider_even_if_synthesis_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingProvider(_FakeProvider):
        async def synthesize(self, *, text: str, voice: str) -> SynthesizedAudio:
            raise RuntimeError("upstream boom")

    fake_provider = _FailingProvider(SynthesizedAudio(file_path=Path("/tmp/x")))
    monkeypatch.setattr(worker_module, "build_provider", lambda name, settings: fake_provider)
    monkeypatch.setattr(
        worker_module,
        "report_progress",
        _async_noop,
    )

    with pytest.raises(RuntimeError, match="upstream boom"):
        await synthesize_job(_job(), authorization=None)

    assert fake_provider.closed is True


async def _async_noop(*args: Any, **kwargs: Any) -> None:
    return None


class _FakeProcessContext:
    def __init__(self, message: _FakeMessage) -> None:
        self._message = message

    async def __aenter__(self) -> _FakeMessage:
        return self._message

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        if exc_type is None:
            self._message.acked = True
        else:
            self._message.rejected = True
        return False


class _FakeMessage:
    def __init__(self, body: dict[str, Any], headers: dict[str, Any] | None = None) -> None:
        self.body = json.dumps(body).encode("utf-8")
        self.headers = headers
        self.acked = False
        self.rejected = False

    def process(self, *, ignore_processed: bool = False) -> _FakeProcessContext:
        return _FakeProcessContext(self)


async def test_handle_message_acks_on_successful_synthesis(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    result = SynthesizedAudio(file_path=tmp_path / "out.mp3")
    monkeypatch.setattr(worker_module, "synthesize_job", _async_return(result))
    message = _FakeMessage(
        {
            "jobId": "job-1",
            "text": "hello",
            "voice": "qwen-voice-a",
            "genUploadUrl": "https://client.example.com/upload",
            "statusCallbackUrl": "https://client.example.com/status",
        },
        headers={"authorization": "Bearer secret"},
    )

    await handle_message(message)  # type: ignore[arg-type]

    assert message.acked is True
    assert message.rejected is False


async def test_handle_message_rejects_and_reraises_on_synthesis_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fail(*args: Any, **kwargs: Any) -> SynthesizedAudio:
        raise RuntimeError("upstream boom")

    monkeypatch.setattr(worker_module, "synthesize_job", _fail)
    message = _FakeMessage(
        {
            "jobId": "job-1",
            "text": "hello",
            "voice": "qwen-voice-a",
            "genUploadUrl": "https://client.example.com/upload",
            "statusCallbackUrl": "https://client.example.com/status",
        }
    )

    with pytest.raises(RuntimeError, match="upstream boom"):
        await handle_message(message)  # type: ignore[arg-type]

    assert message.rejected is True
    assert message.acked is False


def _async_return(value: Any):
    async def _fn(*args: Any, **kwargs: Any) -> Any:
        return value

    return _fn
