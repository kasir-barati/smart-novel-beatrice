from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.modules.audio import worker as worker_module
from src.modules.audio.types import GenerateAudioJob, SynthesizedAudio, SynthesizeErrorCode
from src.modules.audio.worker import (
    GENERATING_CALL_PERCENT,
    GENERATING_STARTED_PERCENT,
    handle_message,
    report_completed,
    report_failed,
    report_progress,
    synthesize_job,
    upload_job,
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
    def __init__(self, status_code: int, json_body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._json_body = json_body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)  # type: ignore[arg-type]

    def json(self) -> dict[str, Any]:
        assert self._json_body is not None
        return self._json_body


class _FakeHttpxClient:
    def __init__(
        self,
        calls: list[dict[str, Any]],
        *,
        fail: bool = False,
        json_body: dict[str, Any] | None = None,
    ) -> None:
        self._calls = calls
        self._fail = fail
        self._json_body = json_body

    async def __aenter__(self) -> _FakeHttpxClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(
        self, url: str, *, json: dict[str, Any] | None = None, headers: dict[str, str]
    ) -> _FakeHttpxResponse:
        self._calls.append({"method": "POST", "url": url, "json": json, "headers": headers})
        if self._fail:
            raise httpx.ConnectError("connection refused")
        return _FakeHttpxResponse(200, self._json_body)

    async def put(self, url: str, *, content: bytes, headers: dict[str, str]) -> _FakeHttpxResponse:
        self._calls.append({"method": "PUT", "url": url, "content": content, "headers": headers})
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
            "method": "POST",
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


async def test_report_completed_posts_status_and_file_size(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        worker_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls, fail=False)
    )

    await report_completed(
        "http://client.example.com/status",
        file_size_bytes=4096,
        authorization=None,
        job_id="job-1",
    )

    assert calls[0]["json"] == {"status": "completed", "fileSizeBytes": 4096}


async def test_report_failed_posts_status_error_code_and_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        worker_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls, fail=False)
    )

    await report_failed(
        "http://client.example.com/status",
        code=SynthesizeErrorCode.UPLOAD_ERROR,
        message="boom",
        authorization=None,
        job_id="job-1",
    )

    body = calls[0]["json"]
    assert body["status"] == "failed"
    assert "failedAt" in body
    assert body["error"] == {"code": "UPLOAD_ERROR", "message": "boom"}


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
    monkeypatch.setattr(worker_module, "report_progress", _async_noop)

    with pytest.raises(RuntimeError, match="upstream boom"):
        await synthesize_job(_job(), authorization=None)

    assert fake_provider.closed is True


async def test_upload_job_fetches_presigned_url_and_puts_the_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    file_path = tmp_path / "out.mp3"
    file_path.write_bytes(b"abcde")
    audio = SynthesizedAudio(file_path=file_path)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        worker_module.httpx,
        "AsyncClient",
        lambda **_: _FakeHttpxClient(
            calls, json_body={"url": "https://storage.example.com/presigned"}
        ),
    )
    progress_calls: list[dict[str, Any]] = []

    async def _fake_report_progress(url: str, *, status: str, percent: int, **kwargs: Any) -> None:
        progress_calls.append({"status": status, "percent": percent})

    monkeypatch.setattr(worker_module, "report_progress", _fake_report_progress)

    file_size = await upload_job(_job(), audio, authorization="Bearer secret")

    assert file_size == 5
    assert progress_calls == [{"status": "uploading", "percent": 0}]
    post_call = next(c for c in calls if c["method"] == "POST")
    assert post_call["url"] == "https://client.example.com/upload"
    assert post_call["headers"] == {"Idempotency-Key": "job-1", "authorization": "Bearer secret"}
    put_call = next(c for c in calls if c["method"] == "PUT")
    assert put_call["url"] == "https://storage.example.com/presigned"
    assert put_call["content"] == b"abcde"
    assert put_call["headers"] == {"Content-Type": "audio/mpeg"}


async def test_upload_job_rejects_a_gen_upload_url_not_on_the_allow_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    audio = SynthesizedAudio(file_path=tmp_path / "out.mp3")
    monkeypatch.setattr(worker_module, "report_progress", _async_noop)

    with pytest.raises(worker_module.CallbackUrlNotAllowedError):
        await upload_job(
            _job(genUploadUrl="https://evil.example.com/upload"), audio, authorization=None
        )


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


def _message() -> _FakeMessage:
    return _FakeMessage(
        {
            "jobId": "job-1",
            "text": "hello",
            "voice": "qwen-voice-a",
            "genUploadUrl": "https://client.example.com/upload",
            "statusCallbackUrl": "https://client.example.com/status",
        }
    )


async def test_handle_message_acks_and_reports_completed_on_full_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    audio = SynthesizedAudio(file_path=tmp_path / "out.mp3")
    monkeypatch.setattr(worker_module, "synthesize_job", _async_return(audio))
    monkeypatch.setattr(worker_module, "upload_job", _async_return(1234))
    completed_calls: list[dict[str, Any]] = []

    async def _fake_report_completed(url: str, *, file_size_bytes: int, **kwargs: Any) -> None:
        completed_calls.append({"url": url, "file_size_bytes": file_size_bytes})

    monkeypatch.setattr(worker_module, "report_completed", _fake_report_completed)
    message = _message()

    await handle_message(message)  # type: ignore[arg-type]

    assert message.acked is True
    assert message.rejected is False
    assert completed_calls == [
        {"url": "https://client.example.com/status", "file_size_bytes": 1234}
    ]


async def test_handle_message_reports_failed_with_provider_code_on_synthesis_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fail(*args: Any, **kwargs: Any) -> SynthesizedAudio:
        raise RuntimeError("upstream boom")

    monkeypatch.setattr(worker_module, "synthesize_job", _fail)
    failed_calls: list[dict[str, Any]] = []

    async def _fake_report_failed(url: str, *, code, message, **kwargs: Any) -> None:
        failed_calls.append({"code": code, "message": message})

    monkeypatch.setattr(worker_module, "report_failed", _fake_report_failed)
    message = _message()

    with pytest.raises(RuntimeError, match="upstream boom"):
        await handle_message(message)  # type: ignore[arg-type]

    assert message.rejected is True
    assert message.acked is False
    assert failed_calls == [
        {"code": SynthesizeErrorCode.TTS_PROVIDER_ERROR, "message": "upstream boom"}
    ]


async def test_handle_message_reports_failed_with_upload_code_on_upload_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    audio = SynthesizedAudio(file_path=tmp_path / "out.mp3")
    monkeypatch.setattr(worker_module, "synthesize_job", _async_return(audio))

    async def _fail(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("storage boom")

    monkeypatch.setattr(worker_module, "upload_job", _fail)
    failed_calls: list[dict[str, Any]] = []

    async def _fake_report_failed(url: str, *, code, message, **kwargs: Any) -> None:
        failed_calls.append({"code": code, "message": message})

    monkeypatch.setattr(worker_module, "report_failed", _fake_report_failed)
    message = _message()

    with pytest.raises(RuntimeError, match="storage boom"):
        await handle_message(message)  # type: ignore[arg-type]

    assert message.rejected is True
    assert message.acked is False
    assert failed_calls == [{"code": SynthesizeErrorCode.UPLOAD_ERROR, "message": "storage boom"}]


def _async_return(value: Any):
    async def _fn(*args: Any, **kwargs: Any) -> Any:
        return value

    return _fn
