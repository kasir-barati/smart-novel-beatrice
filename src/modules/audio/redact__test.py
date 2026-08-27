from __future__ import annotations

from src.modules.audio.redact import redact_presigned_url


def test_redact_presigned_url_strips_the_query_string() -> None:
    result = redact_presigned_url(
        "https://storage.example.com/bucket/key.mp3"
        "?X-Amz-Signature=secret&X-Amz-Credential=also-secret"
    )

    assert result == "https://storage.example.com/bucket/key.mp3"


def test_redact_presigned_url_keeps_scheme_host_and_path_unchanged() -> None:
    result = redact_presigned_url("https://storage.example.com:9000/bucket/key.mp3")

    assert result == "https://storage.example.com:9000/bucket/key.mp3"


def test_redact_presigned_url_falls_back_to_the_plain_url_when_redaction_fails() -> None:
    malformed = "http://[::1"

    result = redact_presigned_url(malformed)

    assert result == malformed
