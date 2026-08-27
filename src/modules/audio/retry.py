"""
Retry/DLQ decision logic for the generateAudio worker.
"""

from __future__ import annotations

from typing import NamedTuple

import httpx


class RetryDecision(NamedTuple):
    should_retry: bool
    delay_seconds: float


def decide_retry(exc: Exception, *, default_delay_seconds: float) -> RetryDecision:
    """
    Classify a failure from an outbound HTTP call (the TTS provider, genUploadUrl, or
    the presigned-URL PUT) and decide whether the job should be retried, and after how long.

    - 4xx (except 408/429): the request is malformed/rejected and won't succeed
      unchanged — not retryable. Retrying just burns the attempt budget on something
      that fails identically every time.
    - 408 (Request Timeout) / 429 (Too Many Requests): transient by design — retryable,
      honoring a `Retry-After` header when present instead of always waiting the default.
    - 5xx, and anything with no HTTP status at all (network errors, timeouts,
      connection refused): always retryable — these mean the server or network failed,
      not that our request was invalid.
    """

    status_code = _status_code_of(exc)

    if status_code is None:
        return RetryDecision(should_retry=True, delay_seconds=default_delay_seconds)

    if status_code in (408, 429):
        retry_after = _retry_after_seconds(exc)
        return RetryDecision(
            should_retry=True,
            delay_seconds=retry_after if retry_after is not None else default_delay_seconds,
        )

    if 400 <= status_code < 500:
        return RetryDecision(should_retry=False, delay_seconds=0.0)

    return RetryDecision(should_retry=True, delay_seconds=default_delay_seconds)


def _status_code_of(exc: Exception) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code

    # TtsProviderError (src/modules/audio/exceptions.py) carries its own status_code —
    # duck-typed here rather than imported, to avoid a needless module dependency.
    status_code = getattr(exc, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def _retry_after_seconds(exc: Exception) -> float | None:
    if not isinstance(exc, httpx.HTTPStatusError):
        return None  # TtsProviderError doesn't preserve response headers.

    header = exc.response.headers.get("Retry-After")
    if header is None:
        return None

    try:
        return float(header)
    except ValueError:
        return None  # HTTP-date form isn't handled; fall back to the default delay.
