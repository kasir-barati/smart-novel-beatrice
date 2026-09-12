from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from src.modules.audio import progress as progress_module
from src.modules.audio.types import SynthesizeErrorCode
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
    def __init__(self, calls: list[dict[str, Any]], *, fail: bool = False) -> None:
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


async def test_report_queued_posts_status(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(progress_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls))

    await progress_module.report(
        "http://client.example.com/status",
        "queued",
        job_id="job-1",
        client_context_id=None,
        authorization="Bearer secret",
    )

    assert calls == [
        {
            "url": "http://client.example.com/status",
            "json": {"status": "queued", "jobId": "job-1"},
            "headers": {"authorization": "Bearer secret"},
        }
    ]


async def test_report_generating_posts_status(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(progress_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls))

    await progress_module.report(
        "http://client.example.com/status",
        "generating",
        job_id="job-1",
        client_context_id=None,
        authorization=None,
    )

    assert calls[0]["json"] == {"status": "generating", "jobId": "job-1"}


async def test_report_uploading_posts_status(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(progress_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls))

    await progress_module.report(
        "http://client.example.com/status",
        "uploading",
        job_id="job-1",
        client_context_id=None,
        authorization=None,
    )

    assert calls[0]["json"] == {"status": "uploading", "jobId": "job-1"}


async def test_report_completed_posts_status_and_file_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(progress_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls))

    await progress_module.report(
        "http://client.example.com/status",
        "completed",
        job_id="job-1",
        client_context_id=None,
        authorization=None,
        fileSizeBytes=4096,
    )

    assert calls[0]["json"] == {"status": "completed", "jobId": "job-1", "fileSizeBytes": 4096}


async def test_report_failed_posts_status_error_and_failed_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(progress_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls))

    await progress_module.report(
        "http://client.example.com/status",
        "failed",
        job_id="job-1",
        client_context_id=None,
        authorization=None,
        failedAt="2024-01-01T00:00:00+00:00",
        error={"code": SynthesizeErrorCode.UPLOAD_ERROR.value, "message": "boom"},
    )

    assert calls[0]["json"] == {
        "status": "failed",
        "jobId": "job-1",
        "failedAt": "2024-01-01T00:00:00+00:00",
        "error": {"code": "UPLOAD_ERROR", "message": "boom"},
    }


async def test_report_includes_client_context_id_when_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(progress_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls))

    await progress_module.report(
        "http://client.example.com/status",
        "queued",
        job_id="job-1",
        client_context_id="chapter-42",
        authorization=None,
    )

    assert calls[0]["json"]["clientContextId"] == "chapter-42"


async def test_report_omits_client_context_id_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(progress_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls))

    await progress_module.report(
        "http://client.example.com/status",
        "queued",
        job_id="job-1",
        client_context_id=None,
        authorization=None,
    )

    assert "clientContextId" not in calls[0]["json"]


async def test_report_omits_authorization_header_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(progress_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls))

    await progress_module.report(
        "http://client.example.com/status",
        "queued",
        job_id="job-1",
        client_context_id=None,
        authorization=None,
    )

    assert calls[0]["headers"] == {}


async def test_report_does_not_raise_on_callback_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        progress_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient([], fail=True)
    )

    await progress_module.report(
        "http://client.example.com/status",
        "queued",
        job_id="job-1",
        client_context_id=None,
        authorization=None,
    )


async def test_report_does_not_revalidate_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The resolver's own call doesn't need re-validation — its URL was already checked
    by `validate_callback_url` earlier in the same request, nothing crossed a queue hop."""

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(progress_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls))

    await progress_module.report(
        "https://evil.example.com/status",
        "queued",
        job_id="job-1",
        client_context_id=None,
        authorization=None,
    )

    assert len(calls) == 1


async def test_report_refuses_a_host_not_on_the_allow_list_when_revalidating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(progress_module.httpx, "AsyncClient", lambda **_: _FakeHttpxClient(calls))

    await progress_module.report(
        "https://evil.example.com/status",
        "generating",
        job_id="job-1",
        client_context_id=None,
        authorization=None,
        revalidate=True,
    )

    assert calls == []
