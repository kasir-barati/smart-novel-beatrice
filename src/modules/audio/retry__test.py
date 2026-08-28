from __future__ import annotations

import httpx
import pytest

from src.modules.audio.exceptions import TtsProviderError
from src.modules.audio.retry import decide_retry


def _http_status_error(
    status_code: int, headers: dict[str, str] | None = None
) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com/")
    response = httpx.Response(status_code, headers=headers or {}, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
def test_decide_retry_does_not_retry_4xx_other_than_408_and_429(status_code: int) -> None:
    result = decide_retry(_http_status_error(status_code), default_delay_seconds=30.0)

    assert result.should_retry is False
    assert result.delay_seconds == 0.0


def test_decide_retry_retries_408_with_the_default_delay_when_no_retry_after() -> None:
    result = decide_retry(_http_status_error(408), default_delay_seconds=30.0)

    assert result.should_retry is True
    assert result.delay_seconds == 30.0


def test_decide_retry_retries_429_honoring_retry_after_header() -> None:
    result = decide_retry(
        _http_status_error(429, headers={"Retry-After": "5"}), default_delay_seconds=30.0
    )

    assert result.should_retry is True
    assert result.delay_seconds == 5.0


def test_decide_retry_falls_back_to_default_delay_on_unparseable_retry_after() -> None:
    result = decide_retry(
        _http_status_error(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}),
        default_delay_seconds=30.0,
    )

    assert result.should_retry is True
    assert result.delay_seconds == 30.0


@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
def test_decide_retry_always_retries_5xx(status_code: int) -> None:
    result = decide_retry(_http_status_error(status_code), default_delay_seconds=30.0)

    assert result.should_retry is True
    assert result.delay_seconds == 30.0


def test_decide_retry_retries_a_network_error_with_no_status_code() -> None:
    result = decide_retry(httpx.ConnectError("connection refused"), default_delay_seconds=30.0)

    assert result.should_retry is True
    assert result.delay_seconds == 30.0


def test_decide_retry_retries_a_timeout_with_no_status_code() -> None:
    result = decide_retry(httpx.ConnectTimeout("timed out"), default_delay_seconds=30.0)

    assert result.should_retry is True
    assert result.delay_seconds == 30.0


def test_decide_retry_does_not_retry_a_tts_provider_error_with_a_4xx_status_code() -> None:
    exc = TtsProviderError(provider="qwen3-tts", message="bad request", status_code=400)

    result = decide_retry(exc, default_delay_seconds=30.0)

    assert result.should_retry is False


def test_decide_retry_retries_a_tts_provider_error_with_a_5xx_status_code() -> None:
    exc = TtsProviderError(provider="qwen3-tts", message="server error", status_code=503)

    result = decide_retry(exc, default_delay_seconds=30.0)

    assert result.should_retry is True


def test_decide_retry_treats_tts_provider_error_without_status_code_as_retryable() -> None:
    exc = TtsProviderError(provider="qwen3-tts", message="unknown failure")

    result = decide_retry(exc, default_delay_seconds=30.0)

    assert result.should_retry is True
    assert result.delay_seconds == 30.0
