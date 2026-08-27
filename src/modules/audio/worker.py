"""
Worker: consumes `generateAudio` jobs from RabbitMQ and drives synthesis.

Consume + synthesize only (REQUIREMENTS.md step 4) — upload and terminal-state
reporting are step 5, and proper retry/DLQ handling (instead of the plain
drop-on-failure below) is step 6.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aio_pika
import httpx

from src.modules.audio.provider import build_provider
from src.modules.audio.rabbitmq import QUEUE_ARGUMENTS
from src.modules.audio.types import GenerateAudioJob, SynthesizedAudio
from src.utils import Settings, get_settings


_logger = logging.getLogger(__name__)

GENERATING_STARTED_PERCENT = 0
GENERATING_CALL_PERCENT = 12
"""
Synthesis is a single blocking HTTP call with no real incremental progress today
(Qwen3-TTS's HTTP shim exposes none) — this marks "the provider call has started",
not a measured value.
"""


async def report_progress(
    status_callback_url: str,
    *,
    status: str,
    percent: int,
    authorization: str | None,
    job_id: str,
) -> None:
    """Best-effort — a flaky callback endpoint shouldn't fail job processing."""

    headers = {"authorization": authorization} if authorization is not None else {}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                status_callback_url,
                json={"status": status, "percent": percent},
                headers=headers,
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        _logger.warning(
            "Failed to report progress to statusCallbackUrl",
            extra={
                "job_id": job_id,
                "status": status,
                "percent": percent,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
            exc_info=exc,
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


async def handle_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    """Parse one delivery, synthesize, and ack/nack it. See module docstring for scope."""

    async with message.process(ignore_processed=True):
        body: dict[str, Any] = json.loads(message.body)
        job = GenerateAudioJob.model_validate(body)
        raw_authorization = message.headers.get("authorization") if message.headers else None
        authorization = str(raw_authorization) if raw_authorization is not None else None

        try:
            audio = await synthesize_job(job, authorization=authorization)
        except Exception as exc:
            _logger.warning(
                "Synthesis failed for generateAudio job",
                extra={
                    "job_id": job.job_id,
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                },
                exc_info=exc,
            )
            raise

        _logger.info(
            "Synthesis completed for generateAudio job",
            extra={"job_id": job.job_id, "file_path": str(audio.file_path)},
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
