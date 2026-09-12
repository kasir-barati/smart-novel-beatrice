"""
Resolvers for the audio module's GraphQL surface.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import strawberry
from pydantic import StringConstraints
from pydantic.functional_validators import AfterValidator
from strawberry.types import Info

from src.modules.audio import progress
from src.modules.audio.callback_urls import validate_callback_url
from src.modules.audio.exceptions import InstructNotSupportedError, InvalidVoiceError
from src.modules.audio.provider import build_provider
from src.modules.audio.rabbitmq import publish_generate_audio_job
from src.utils import TtsProviderName, get_settings, spectaql_example


_voices_cache: list[str] | None = None
_voices_cache_lock = asyncio.Lock()


async def resolve_audio_voices() -> list[str]:
    """
    Return the configured provider's voice names, fetched once and cached for the
    lifetime of the process — see `Tts.default_provider` for which provider backs this.
    """

    global _voices_cache

    if _voices_cache is not None:
        return _voices_cache

    async with _voices_cache_lock:
        if _voices_cache is None:
            settings = get_settings()
            provider = build_provider(settings.tts.default_provider, settings)
            try:
                voices = await provider.get_voices()
            finally:
                await provider.aclose()
            _voices_cache = [voice.name for voice in voices]

    return _voices_cache


def _validate_text_length(value: str) -> str:
    max_length = get_settings().generate_audio.max_text_length

    if len(value) > max_length:
        raise ValueError(f"must be at most {max_length} characters (got {len(value)}).")

    return value


@strawberry.type(description="Result of queuing a generateAudio job.")
class GenerateAudioResult:
    job_id: str = strawberry.field(
        description=(
            "UUID identifying this synthesis job. Use it to correlate statusCallbackUrl updates."
        ),
        directives=[spectaql_example("550e8400-e29b-41d4-a716-446655440000")],
    )


async def generate_audio(
    text: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1),
        AfterValidator(_validate_text_length),
        strawberry.argument(
            description="Text to synthesize. Length is capped by the GENERATE_AUDIO__MAX_TEXT_LENGTH env var.",
            directives=[spectaql_example("The graffiti was ephemeral.")],
        ),
    ],
    voice: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1),
        strawberry.argument(description="Voice name — must be one returned by audioVoices."),
    ],
    gen_upload_url: Annotated[
        str,
        AfterValidator(validate_callback_url),
        strawberry.argument(
            description=(
                "Callback Beatrice POSTs to exactly once, when it needs a presigned upload URL "
                "for the synthesized audio. Sent with header `Idempotency-Key: <jobId>`, so a "
                "retried call is recognized as the same request rather than minting a second "
                'presigned URL. Must respond with JSON shaped `{"url": "<presigned-url>"}` — '
                "Beatrice then PUTs the audio bytes directly to that URL with "
                "`Content-Type: audio/mpeg`. Host must be in the "
                "GENERATE_AUDIO__CALLBACK__ALLOWED_HOSTS allow-list. The callback receives a "
                'JSON body `{"clientContextId": "<value>"}` when the caller supplied '
                "`clientContextId`, and no body otherwise."
            ),
        ),
    ],
    status_callback_url: Annotated[
        str,
        AfterValidator(validate_callback_url),
        strawberry.argument(
            description=(
                "Callback Beatrice POSTs progress/state updates to, exactly one call per "
                "status, best-effort (a failed delivery is logged and never fails the job "
                'or blocks retries). Every body includes `"jobId": "<jobId>"`, plus '
                '`"clientContextId": "<value>"` when the caller supplied `clientContextId`. '
                'Bodies, in order: `{"status": "queued", "progress": <int>, "jobId": '
                '"<jobId>", "clientContextId": "<value>"}`; `{"status": "generating", '
                '"progress": <int>, "jobId": "<jobId>", "clientContextId": "<value>"}`; '
                '`{"status": "uploading", "progress": <int>, "jobId": "<jobId>", '
                '"clientContextId": "<value>"}`; then either `{"status": "completed", '
                '"fileSizeBytes": <int>, "jobId": "<jobId>", "clientContextId": "<value>"}` '
                'or `{"status": "failed", "failedAt": "<iso8601>", "error": {"code": '
                '"TTS_PROVIDER_ERROR" | "UPLOAD_ERROR", "message": "<str>"}, "jobId": '
                '"<jobId>", "clientContextId": "<value>"}`. `progress` is present with an '
                "integer value on `queued`/`generating`/`uploading` and absent on "
                '`"completed"`/`"failed"`. It means only "a bigger number is later for this '
                "job\" — no meaning is attached to specific values, and they aren't "
                "guaranteed to stay stable across a Beatrice release. `clientContextId` is "
                "omitted entirely when the caller didn't supply one. No response body is "
                "expected. Host must be in the GENERATE_AUDIO__CALLBACK__ALLOWED_HOSTS "
                "allow-list."
            ),
        ),
    ],
    info: Info,
    instruct: Annotated[
        str | None,
        strawberry.argument(
            description=(
                "Qwen3-TTS-only. A style guide applied to the whole call, e.g. 'A male "
                "narrator with a clear voice. Treat bracketed words like [dramatic] as "
                "emotion cues, not literal text.' text is never parsed or stripped by "
                "Beatrice — any inline tags in it are passed through verbatim for the "
                "model to interpret per this guide. Rejected when the configured "
                "provider isn't Qwen3-TTS. Qwen3-TTS (and therefore instruct) is "
                "English-only for now."
            ),
        ),
    ] = None,
    client_context_id: Annotated[
        str | None,
        strawberry.argument(
            description=(
                "Opaque caller-supplied value. Beatrice never interprets or validates it — "
                "it's stored alongside the job and echoed back verbatim, as "
                "`clientContextId`, in every `statusCallbackUrl` body and in the "
                "`genUploadUrl` POST. Useful for correlating callbacks that may arrive "
                "before the mutation response does."
            ),
        ),
    ] = None,
) -> GenerateAudioResult:
    """generateAudio resolver: validate, publish to RabbitMQ, respond immediately with a jobId."""

    voices = await resolve_audio_voices()

    if voice not in voices:
        raise InvalidVoiceError(voice=voice)

    default_provider = get_settings().tts.default_provider
    if instruct is not None and default_provider is not TtsProviderName.QWEN3_TTS:
        raise InstructNotSupportedError(provider=default_provider)

    request = info.context["request"]
    authorization = request.headers.get("authorization")
    job_id = str(uuid.uuid4())

    message_headers: dict[str, Any] = {"timestamp": datetime.now(UTC).isoformat()}
    if authorization is not None:
        message_headers["authorization"] = authorization

    message_body: dict[str, str] = {
        "jobId": job_id,
        "text": text,
        "voice": voice,
        "genUploadUrl": gen_upload_url,
        "statusCallbackUrl": status_callback_url,
    }
    if instruct is not None:
        message_body["instruct"] = instruct
    if client_context_id is not None:
        message_body["clientContextId"] = client_context_id

    await publish_generate_audio_job(
        settings=get_settings().rabbitmq,
        body=message_body,
        headers=message_headers,
    )
    await progress.report(
        status_callback_url,
        "queued",
        job_id=job_id,
        client_context_id=client_context_id,
        authorization=authorization,
    )

    info.context["response"].status_code = 202

    return GenerateAudioResult(job_id=job_id)
