"""
Resolvers for the audio module's GraphQL surface.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
import strawberry
from pydantic import StringConstraints
from pydantic.functional_validators import AfterValidator
from strawberry.types import Info

from src.modules.audio.callback_urls import validate_callback_url
from src.modules.audio.exceptions import InvalidVoiceError
from src.modules.audio.provider import build_provider
from src.modules.audio.rabbitmq import publish_generate_audio_job
from src.utils import get_settings, spectaql_example


_logger = logging.getLogger(__name__)

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
                "Callback Beatrice POSTs to when it needs a presigned upload URL. Host must be "
                "in the GENERATE_AUDIO__CALLBACK__ALLOWED_HOSTS allow-list."
            ),
        ),
    ],
    status_callback_url: Annotated[
        str,
        AfterValidator(validate_callback_url),
        strawberry.argument(
            description=(
                "Callback Beatrice POSTs progress/state updates to. Host must be in the "
                "GENERATE_AUDIO__CALLBACK__ALLOWED_HOSTS allow-list."
            ),
        ),
    ],
    info: Info,
) -> GenerateAudioResult:
    """generateAudio resolver: validate, publish to RabbitMQ, respond immediately with a jobId."""

    voices = await resolve_audio_voices()

    if voice not in voices:
        raise InvalidVoiceError(voice=voice)

    request = info.context["request"]
    authorization = request.headers.get("authorization")
    job_id = str(uuid.uuid4())

    message_headers: dict[str, Any] = {"timestamp": datetime.now(UTC).isoformat()}
    if authorization is not None:
        message_headers["authorization"] = authorization

    message_body = {
        "jobId": job_id,
        "text": text,
        "voice": voice,
        "genUploadUrl": gen_upload_url,
        "statusCallbackUrl": status_callback_url,
    }

    await publish_generate_audio_job(
        settings=get_settings().rabbitmq,
        body=message_body,
        headers=message_headers,
    )
    await _report_queued(job_id, status_callback_url, authorization=authorization)

    info.context["response"].status_code = 202

    return GenerateAudioResult(job_id=job_id)


async def _report_queued(
    job_id: str, status_callback_url: str, *, authorization: str | None
) -> None:
    """
    Best-effort — the job is already durably published by the time this runs, so a flaky
    callback endpoint shouldn't fail the mutation or drop the job.
    """

    headers = {"authorization": authorization} if authorization is not None else {}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                status_callback_url, json={"status": "queued"}, headers=headers
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        _logger.warning(
            "Failed to report 'queued' status to statusCallbackUrl",
            extra={
                "job_id": job_id,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
            exc_info=exc,
        )
