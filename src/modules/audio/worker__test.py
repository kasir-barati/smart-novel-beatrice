from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import aio_pika
import httpx
import pytest

from src.modules.audio import worker as worker_module
from src.modules.audio.types import GenerateAudioJob, SynthesizedAudio, SynthesizeErrorCode
from src.modules.audio.worker import (
    handle_message,
    report_completed,
    report_failed,
    report_progress,
    synthesize_job,
    upload_job,
)
from src.utils import RabbitMq, Settings, get_settings


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


def _record_progress_report(sink: list[dict[str, Any]]):
    async def _fn(
        url: str,
        status: str,
        *,
        job_id: str,
        client_context_id: str | None,
        authorization: str | None,
        revalidate: bool = False,
        **extra: Any,
    ) -> None:
        sink.append(
            {
                "url": url,
                "status": status,
                "job_id": job_id,
                "client_context_id": client_context_id,
                "authorization": authorization,
                "revalidate": revalidate,
                **extra,
            }
        )

    return _fn


async def test_report_progress_delegates_to_progress_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(worker_module.progress, "report", _record_progress_report(calls))

    await report_progress(
        "http://client.example.com/status",
        status="generating",
        authorization="Bearer secret",
        job_id="2bce49d6-6592-4ed3-b421-f913b9ecc3bd",
        client_context_id="chapter-42",
    )

    assert calls == [
        {
            "url": "http://client.example.com/status",
            "status": "generating",
            "job_id": "2bce49d6-6592-4ed3-b421-f913b9ecc3bd",
            "client_context_id": "chapter-42",
            "authorization": "Bearer secret",
            "revalidate": True,
        }
    ]


async def test_report_completed_delegates_to_progress_report_with_file_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(worker_module.progress, "report", _record_progress_report(calls))

    await report_completed(
        "http://client.example.com/status",
        file_size_bytes=4096,
        authorization=None,
        job_id="2bce49d6-6592-4ed3-b421-f913b9ecc3bd",
        client_context_id=None,
    )

    assert calls == [
        {
            "url": "http://client.example.com/status",
            "status": "completed",
            "job_id": "2bce49d6-6592-4ed3-b421-f913b9ecc3bd",
            "client_context_id": None,
            "authorization": None,
            "revalidate": True,
            "fileSizeBytes": 4096,
        }
    ]


async def test_report_failed_delegates_to_progress_report_with_error_and_failed_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(worker_module.progress, "report", _record_progress_report(calls))

    await report_failed(
        "http://client.example.com/status",
        code=SynthesizeErrorCode.UPLOAD_ERROR,
        message="boom",
        authorization=None,
        job_id="2bce49d6-6592-4ed3-b421-f913b9ecc3bd",
        client_context_id=None,
    )

    assert len(calls) == 1
    call = calls[0]
    assert call["status"] == "failed"
    assert call["revalidate"] is True
    assert call["error"] == {"code": "UPLOAD_ERROR", "message": "boom"}
    assert "failedAt" in call


class _FakeProvider:
    def __init__(self, result: SynthesizedAudio) -> None:
        self._result = result
        self.synthesize_calls: list[dict[str, Any]] = []
        self.closed = False

    async def get_voices(self, *, language: str | None = None):  # pragma: no cover - unused here
        raise NotImplementedError

    async def synthesize(
        self, *, text: str, voice: str, instruct: str | None = None
    ) -> SynthesizedAudio:
        self.synthesize_calls.append({"text": text, "voice": voice, "instruct": instruct})
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

    async def _fake_report_progress(
        url: str, *, status: str, client_context_id: str | None, **kwargs: Any
    ) -> None:
        progress_calls.append(
            {"url": url, "status": status, "client_context_id": client_context_id}
        )

    monkeypatch.setattr(worker_module, "report_progress", _fake_report_progress)

    job = _job(clientContextId="chapter-42")
    returned = await synthesize_job(job, authorization=None)

    assert returned is result
    assert fake_provider.synthesize_calls == [
        {"text": "hello", "voice": "qwen-voice-a", "instruct": None}
    ]
    assert fake_provider.closed is True
    assert progress_calls == [
        {
            "url": job.status_callback_url,
            "status": "generating",
            "client_context_id": "chapter-42",
        }
    ]


async def test_synthesize_job_forwards_instruct_to_the_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    result = SynthesizedAudio(file_path=tmp_path / "out.mp3")
    fake_provider = _FakeProvider(result)
    monkeypatch.setattr(worker_module, "build_provider", lambda name, settings: fake_provider)
    monkeypatch.setattr(worker_module, "report_progress", _async_noop)

    job = _job(instruct="speak in a whisper")
    await synthesize_job(job, authorization=None)

    assert fake_provider.synthesize_calls == [
        {"text": "hello", "voice": "qwen-voice-a", "instruct": "speak in a whisper"}
    ]


async def test_synthesize_job_closes_the_provider_even_if_synthesis_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingProvider(_FakeProvider):
        async def synthesize(
            self, *, text: str, voice: str, instruct: str | None = None
        ) -> SynthesizedAudio:
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

    async def _fake_report_progress(
        url: str, *, status: str, client_context_id: str | None, **kwargs: Any
    ) -> None:
        progress_calls.append({"status": status, "client_context_id": client_context_id})

    monkeypatch.setattr(worker_module, "report_progress", _fake_report_progress)

    file_size = await upload_job(
        _job(clientContextId="chapter-42"), audio, authorization="Bearer secret"
    )

    assert file_size == 5
    assert progress_calls == [{"status": "uploading", "client_context_id": "chapter-42"}]
    post_call = next(c for c in calls if c["method"] == "POST")
    assert post_call["url"] == "https://client.example.com/upload"
    assert post_call["headers"] == {"Idempotency-Key": "job-1", "authorization": "Bearer secret"}
    assert post_call["json"] == {"clientContextId": "chapter-42"}
    put_call = next(c for c in calls if c["method"] == "PUT")
    assert put_call["url"] == "https://storage.example.com/presigned"
    assert put_call["content"] == b"abcde"
    assert put_call["headers"] == {"Content-Type": "audio/mpeg"}


async def test_upload_job_sends_no_body_to_gen_upload_url_when_client_context_id_absent(
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
    monkeypatch.setattr(worker_module, "report_progress", _async_noop)

    await upload_job(_job(), audio, authorization="Bearer secret")

    post_call = next(c for c in calls if c["method"] == "POST")
    assert post_call["json"] is None


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
    def __init__(
        self,
        body: dict[str, Any],
        headers: dict[str, Any] | None = None,
        content_type: str | None = "application/json",
    ) -> None:
        self.body = json.dumps(body).encode("utf-8")
        self.headers = headers
        self.content_type = content_type
        self.acked = False
        self.rejected = False

    def process(self, *, ignore_processed: bool = False) -> _FakeProcessContext:
        return _FakeProcessContext(self)


def _message(headers: dict[str, Any] | None = None) -> _FakeMessage:
    return _FakeMessage(
        {
            "jobId": "job-1",
            "text": "hello",
            "voice": "qwen-voice-a",
            "genUploadUrl": "https://client.example.com/upload",
            "statusCallbackUrl": "https://client.example.com/status",
        },
        headers=headers,
    )


class _FakePublished:
    def __init__(self, message: aio_pika.Message, routing_key: str) -> None:
        self.message = message
        self.routing_key = routing_key


class _FakeExchange:
    def __init__(self, published: list[_FakePublished]) -> None:
        self._published = published

    async def publish(self, message: aio_pika.Message, *, routing_key: str) -> None:
        self._published.append(_FakePublished(message, routing_key))


class _FakeChannel:
    def __init__(self) -> None:
        self.published: list[_FakePublished] = []
        self.default_exchange = _FakeExchange(self.published)


async def _handle_message(
    message: _FakeMessage, *, channel: _FakeChannel, settings: Settings
) -> None:
    """`handle_message` only touches `.body`/`.headers`/`.content_type`/`.process()` on the
    message and `.default_exchange.publish()` on the channel — these fakes duck-type both."""

    await handle_message(
        cast(aio_pika.abc.AbstractIncomingMessage, message),
        channel=cast(aio_pika.abc.AbstractChannel, channel),
        settings=settings,
    )


def _settings(*, delivery_limit: int = 3, retry_delay_seconds: float = 0.0) -> Settings:
    return Settings(
        rabbitmq=RabbitMq(
            connection_string="amqp://guest:guest@rabbitmq:5672/",
            queue_name="beatrice.generate_audio",
            dlq_name="beatrice.generate_audio.dlq",
            delivery_limit=delivery_limit,
            retry_delay_seconds=retry_delay_seconds,
        )
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
    channel = _FakeChannel()

    await _handle_message(message, channel=channel, settings=_settings())

    assert message.acked is True
    assert message.rejected is False
    assert channel.published == []
    assert completed_calls == [
        {"url": "https://client.example.com/status", "file_size_bytes": 1234}
    ]


async def test_handle_message_retries_a_retryable_synthesis_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fail(*args: Any, **kwargs: Any) -> SynthesizedAudio:
        raise httpx.ConnectError("connection refused")  # no status code -> always retryable

    monkeypatch.setattr(worker_module, "synthesize_job", _fail)
    monkeypatch.setattr(worker_module, "report_failed", _async_noop)
    message = _message()
    channel = _FakeChannel()

    await _handle_message(
        message,
        channel=channel,
        settings=_settings(delivery_limit=3),
    )

    assert message.acked is True
    assert message.rejected is False
    assert len(channel.published) == 1
    published = channel.published[0]
    assert published.routing_key == "beatrice.generate_audio"
    assert published.message.headers["x-attempt"] == 2


async def test_handle_message_sends_a_non_retryable_upload_failure_straight_to_the_dlq(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    audio = SynthesizedAudio(file_path=tmp_path / "out.mp3")
    monkeypatch.setattr(worker_module, "synthesize_job", _async_return(audio))

    async def _fail(*args: Any, **kwargs: Any) -> int:
        raise _http_status_error(400)

    monkeypatch.setattr(worker_module, "upload_job", _fail)
    failed_calls: list[dict[str, Any]] = []

    async def _fake_report_failed(url: str, *, code: Any, message: str, **kwargs: Any) -> None:
        failed_calls.append({"code": code, "message": message})

    monkeypatch.setattr(worker_module, "report_failed", _fake_report_failed)
    message = _message()
    channel = _FakeChannel()

    await _handle_message(
        message,
        channel=channel,
        settings=_settings(delivery_limit=3),
    )

    assert message.acked is True
    assert failed_calls == [
        {"code": SynthesizeErrorCode.UPLOAD_ERROR, "message": str(_http_status_error(400))}
    ]
    assert len(channel.published) == 1
    assert channel.published[0].routing_key == "beatrice.generate_audio.dlq"


async def test_handle_message_sends_an_upload_allow_list_failure_straight_to_the_dlq(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """
    `upload_job` re-validates `genUploadUrl` against the allow-list before calling out.
    A URL that fails this check will fail identically on every retry, so — like any
    other non-retryable failure — it must go straight to the DLQ on the first attempt,
    not consume the retry budget the way an unclassified error would.
    """

    audio = SynthesizedAudio(file_path=tmp_path / "out.mp3")
    monkeypatch.setattr(worker_module, "synthesize_job", _async_return(audio))
    monkeypatch.setattr(worker_module, "report_failed", _async_noop)
    message = _message()
    message.body = json.dumps(
        {
            "jobId": "job-1",
            "text": "hello",
            "voice": "qwen-voice-a",
            "genUploadUrl": "https://evil.example.com/upload",
            "statusCallbackUrl": "https://client.example.com/status",
        }
    ).encode("utf-8")
    channel = _FakeChannel()

    await _handle_message(
        message,
        channel=channel,
        settings=_settings(delivery_limit=3),
    )

    assert message.acked is True
    assert len(channel.published) == 1
    assert channel.published[0].routing_key == "beatrice.generate_audio.dlq"


async def test_handle_message_sends_a_malformed_message_straight_to_the_dlq(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    A body that doesn't parse as JSON or validate as `GenerateAudioJob` has no `job` to
    report failure through (no `statusCallbackUrl` to call) and will fail identically on
    every redelivery, so it must be acked and dead-lettered directly, with a structured
    log line, rather than propagating out of `message.process()` untraced.
    """

    message = _FakeMessage({"jobId": "job-1"})  # missing required fields
    channel = _FakeChannel()

    with caplog.at_level("WARNING"):
        await _handle_message(message, channel=channel, settings=_settings(delivery_limit=3))

    assert message.acked is True
    assert message.rejected is False
    assert len(channel.published) == 1
    assert channel.published[0].routing_key == "beatrice.generate_audio.dlq"
    record: Any = next(
        r
        for r in caplog.records
        if r.message == "generateAudio message could not be parsed — sending to DLQ"
    )
    assert record.error_code == "MALFORMED_MESSAGE"


async def test_handle_message_sends_to_dlq_once_the_delivery_limit_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fail(*args: Any, **kwargs: Any) -> SynthesizedAudio:
        raise httpx.ConnectError("connection refused")  # retryable, but out of attempts

    monkeypatch.setattr(worker_module, "synthesize_job", _fail)
    monkeypatch.setattr(worker_module, "report_failed", _async_noop)
    message = _message(headers={"x-attempt": 2})
    channel = _FakeChannel()

    await _handle_message(
        message,
        channel=channel,
        settings=_settings(delivery_limit=2),
    )

    assert message.acked is True
    assert len(channel.published) == 1
    assert channel.published[0].routing_key == "beatrice.generate_audio.dlq"


async def test_handle_message_success_log_contains_all_required_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    audio = SynthesizedAudio(file_path=tmp_path / "out.mp3")
    monkeypatch.setattr(worker_module, "synthesize_job", _async_return(audio))
    monkeypatch.setattr(worker_module, "upload_job", _async_return(2048))
    monkeypatch.setattr(worker_module, "report_completed", _async_noop)
    message = _message(headers={"timestamp": "2024-01-01T00:00:00+00:00"})
    channel = _FakeChannel()

    with caplog.at_level("INFO"):
        await _handle_message(message, channel=channel, settings=_settings(delivery_limit=3))

    record: Any = next(r for r in caplog.records if r.message == "generateAudio job completed")
    assert record.job_id == "job-1"
    assert record.instance_id
    assert record.voice == "qwen-voice-a"
    assert record.model == "qwen3-tts"
    assert record.state == "completed"
    assert record.attempt == 1
    assert record.max_attempt == 3
    assert record.text_character_count == len("hello")
    assert record.queue_wait_seconds >= 0
    assert record.processing_seconds >= 0
    assert record.total_seconds >= 0
    assert record.file_size_bytes == 2048


async def test_handle_message_failure_log_contains_all_required_fields(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def _fail(*args: Any, **kwargs: Any) -> SynthesizedAudio:
        raise _http_status_error(400)  # non-retryable

    monkeypatch.setattr(worker_module, "synthesize_job", _fail)
    monkeypatch.setattr(worker_module, "report_failed", _async_noop)
    message = _message(headers={"timestamp": "2024-01-01T00:00:00+00:00"})
    channel = _FakeChannel()

    with caplog.at_level("WARNING"):
        await _handle_message(message, channel=channel, settings=_settings(delivery_limit=3))

    record: Any = next(r for r in caplog.records if r.message == "generateAudio job failed")
    assert record.job_id == "job-1"
    assert record.instance_id
    assert record.voice == "qwen-voice-a"
    assert record.model == "qwen3-tts"
    assert record.state == "generating"
    assert record.attempt == 1
    assert record.max_attempt == 3
    assert record.text_character_count == len("hello")
    assert record.queue_wait_seconds >= 0
    assert record.processing_seconds >= 0
    assert record.error_code == "TTS_PROVIDER_ERROR"
    assert record.error_message


def test_queue_wait_seconds_returns_none_when_timestamp_header_is_missing() -> None:
    message = _message()

    result = worker_module._queue_wait_seconds(message)  # type: ignore[arg-type]

    assert result is None


def test_queue_wait_seconds_returns_none_when_timestamp_header_is_unparseable() -> None:
    message = _message(headers={"timestamp": "not-a-date"})

    result = worker_module._queue_wait_seconds(message)  # type: ignore[arg-type]

    assert result is None


def test_queue_wait_seconds_computes_elapsed_time_since_the_header() -> None:
    five_seconds_ago = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    message = _message(headers={"timestamp": five_seconds_ago})

    result = worker_module._queue_wait_seconds(message)  # type: ignore[arg-type]

    assert result is not None
    assert result >= 5


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com/")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


def _async_return(value: Any):
    async def _fn(*args: Any, **kwargs: Any) -> Any:
        return value

    return _fn
