"""
Shared allow-list validation for outbound calls to client-controlled callback URLs
(`genUploadUrl`, `statusCallbackUrl`).

Used both where a callback URL first enters the system (the `generateAudio` mutation)
and anywhere it's read back and used again after crossing a trust boundary (the worker,
consuming it off the RabbitMQ queue) — a queue message isn't proof the URL was actually
validated by whoever/whatever published it, so it's re-checked at the point of use too,
not just once at the edge.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from src.utils import get_settings


class CallbackUrlNotAllowedError(ValueError):
    """
    Raised when a callback URL fails the scheme/host allow-list check.

    Carries a `status_code` of 400 (duck-typed, like `TtsProviderError`) so
    `src.modules.audio.retry.decide_retry` classifies it as a non-retryable client
    error rather than falling into the "no status code" branch reserved for genuine
    network failures — a URL that fails allow-list validation fails identically on
    every retry, so it should go straight to the DLQ.
    """

    status_code = 400


def validate_callback_url(value: str) -> str:
    parsed = urlsplit(value)

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CallbackUrlNotAllowedError("must be an absolute http(s) URL.")

    allowed_hosts = get_settings().generate_audio.callback.allowed_hosts_list

    if parsed.hostname not in allowed_hosts:
        raise CallbackUrlNotAllowedError(f"host '{parsed.hostname}' is not in the allow-list.")

    return value
