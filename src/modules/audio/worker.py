"""
Worker: consumes `generateAudio` jobs from RabbitMQ, drives synthesis, uploads the
result, and reports terminal state (REQUIREMENTS.md steps 4-5).

Proper retry/DLQ handling (instead of the plain drop-on-failure below) is step 6.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import aio_pika
import httpx

from src.modules.audio.callback_urls import CallbackUrlNotAllowedError, validate_callback_url
from src.modules.audio.provider import build_provider
from src.modules.audio.rabbitmq import QUEUE_ARGUMENTS
from src.modules.audio.types import GenerateAudioJob, SynthesizedAudio, SynthesizeErrorCode
from src.utils import Settings, get_settings


_logger = logging.getLogger(__name__)

GENERATING_STARTED_PERCENT = 0
GENERATING_CALL_PERCENT = 12
"""
Synthesis is a single blocking HTTP call with no real incremental progress today
(Qwen3-TTS's HTTP shim exposes none) — this marks "the provider call has started",
not a measured value.
"""

UPLOADING_STARTED_PERCENT = 0

_UPLOAD_CONTENT_TYPE = "audio/mpeg"


async def _post_status_update(
    status_callback_url: str,
    body: dict[str, Any],
    *,
    authorization: str | None,
    job_id: str,
) -> None:
    """
    Best-effort — a flaky callback endpoint shouldn't fail job processing.

    Re-validates the host allow-list before calling out: this URL was already checked
    once by the `generateAudio` mutation, but that check doesn't carry across the
    RabbitMQ hop — this process has no way to know the message wasn't tampered with or
    published some other way, so it re-checks rather than trusting the queue.
    """

    try:
        validate_callback_url(status_callback_url)
    except CallbackUrlNotAllowedError as exc:
        _logger.warning(
            "Refusing to call statusCallbackUrl: failed allow-list re-validation",
            extra={"job_id": job_id, "body": body, "exception_message": str(exc)},
        )
        return

    headers = {"authorization": authorization} if authorization is not None else {}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(status_callback_url, json=body, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        _logger.warning(
            "Failed to call statusCallbackUrl",
            extra={
                "job_id": job_id,
                "body": body,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
            exc_info=exc,
        )


async def report_progress(
    status_callback_url: str,
    *,
    status: str,
    percent: int,
    authorization: str | None,
    job_id: str,
) -> None:
    await _post_status_update(
        status_callback_url,
        {"status": status, "percent": percent},
        authorization=authorization,
        job_id=job_id,
    )


async def report_completed(
    status_callback_url: str,
    *,
    file_size_bytes: int,
    authorization: str | None,
    job_id: str,
) -> None:
    await _post_status_update(
        status_callback_url,
        {"status": "completed", "fileSizeBytes": file_size_bytes},
        authorization=authorization,
        job_id=job_id,
    )


async def report_failed(
    status_callback_url: str,
    *,
    code: SynthesizeErrorCode,
    message: str,
    authorization: str | None,
    job_id: str,
) -> None:
    await _post_status_update(
        status_callback_url,
        {
            "status": "failed",
            "failedAt": datetime.now(UTC).isoformat(),
            "error": {"code": code.value, "message": message},
        },
        authorization=authorization,
        job_id=job_id,
    )


async def synthesize_job(job: GenerateAudioJob, *, authorization: str | None) -> SynthesizedAudio:
    """Report generating progress and call the configured TTS provider for audio bytes."""

    settings = get_settings()

    await report_progress(
        job.status_callback_url,
        status="generating",
        percent=GENERATING_STARTED_PERCENT,
        authorization=authorization,
        job_id=job.job_id,
    )

    provider = build_provider(settings.tts.default_provider, settings)
    try:
        await report_progress(
            job.status_callback_url,
            status="generating",
            percent=GENERATING_CALL_PERCENT,
            authorization=authorization,
            job_id=job.job_id,
        )
        return await provider.synthesize(text=job.text, voice=job.voice)
    finally:
        await provider.aclose()


async def _fetch_presigned_upload_url(
    gen_upload_url: str, *, job_id: str, authorization: str | None
) -> str:
    """
    POST to `genUploadUrl` for a fresh presigned URL, keyed by `Idempotency-Key` so a
    retried call is recognized as the same request rather than minting a second one.

    Assumes the response is JSON shaped `{"url": "<presigned-url>"}` — undocumented on
    the client side of this contract, so this is our own assumption, not a confirmed spec.
    """

    headers = {"Idempotency-Key": job_id}
    if authorization is not None:
        headers["authorization"] = authorization

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(gen_upload_url, headers=headers)
        response.raise_for_status()

    payload = response.json()
    return payload["url"]


async def upload_job(
    job: GenerateAudioJob, audio: SynthesizedAudio, *, authorization: str | None
) -> int:
    """
    Fetch a presigned URL and PUT the synthesized audio to it. Returns the uploaded
    file size in bytes.
    """

    # Same re-validation reasoning as _post_status_update — genUploadUrl crossed the
    # same queue hop and needs the same defense-in-depth check before we call out to it.
    validate_callback_url(job.gen_upload_url)

    await report_progress(
        job.status_callback_url,
        status="uploading",
        percent=UPLOADING_STARTED_PERCENT,
        authorization=authorization,
        job_id=job.job_id,
    )

    presigned_url = await _fetch_presigned_upload_url(
        job.gen_upload_url, job_id=job.job_id, authorization=authorization
    )
    audio_bytes = audio.file_path.read_bytes()

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.put(
            presigned_url,
            content=audio_bytes,
            headers={"Content-Type": _UPLOAD_CONTENT_TYPE},
        )
        response.raise_for_status()

    return len(audio_bytes)


async def handle_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    """Parse one delivery, run the full pipeline, and ack/nack it. See module docstring."""

    async with message.process(ignore_processed=True):
        body: dict[str, Any] = json.loads(message.body)
        job = GenerateAudioJob.model_validate(body)
        raw_authorization = message.headers.get("authorization") if message.headers else None
        authorization = str(raw_authorization) if raw_authorization is not None else None

        try:
            audio = await synthesize_job(job, authorization=authorization)
        except Exception as exc:
            await _fail_job(
                job,
                code=SynthesizeErrorCode.TTS_PROVIDER_ERROR,
                exc=exc,
                authorization=authorization,
            )
            raise

        try:
            file_size_bytes = await upload_job(job, audio, authorization=authorization)
        except Exception as exc:
            await _fail_job(
                job, code=SynthesizeErrorCode.UPLOAD_ERROR, exc=exc, authorization=authorization
            )
            raise

        await report_completed(
            job.status_callback_url,
            file_size_bytes=file_size_bytes,
            authorization=authorization,
            job_id=job.job_id,
        )
        _logger.info(
            "generateAudio job completed",
            extra={"job_id": job.job_id, "file_size_bytes": file_size_bytes},
        )


async def _fail_job(
    job: GenerateAudioJob,
    *,
    code: SynthesizeErrorCode,
    exc: Exception,
    authorization: str | None,
) -> None:
    _logger.warning(
        "generateAudio job failed",
        extra={
            "job_id": job.job_id,
            "error_code": code.value,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        },
        exc_info=exc,
    )
    await report_failed(
        job.status_callback_url,
        code=code,
        message=str(exc),
        authorization=authorization,
        job_id=job.job_id,
    )


async def run_worker(settings: Settings | None = None) -> None:
    """Connect to RabbitMQ and consume `generateAudio` jobs until cancelled."""

    settings = settings or get_settings()
    connection = await aio_pika.connect_robust(settings.rabbitmq.connection_string)

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=settings.rabbitmq.prefetch_count)
        queue = await channel.declare_queue(
            settings.rabbitmq.queue_name,
            durable=True,
            arguments=QUEUE_ARGUMENTS,
        )
        await queue.consume(handle_message)

        await asyncio.Future()  # run until the task is cancelled
