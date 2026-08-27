"""
RabbitMQ publisher for the `generateAudio` job queue.
"""

from __future__ import annotations

import json
from typing import Any

import aio_pika

from src.utils import RabbitMq


QUEUE_ARGUMENTS: dict[str, Any] = {"x-queue-type": "quorum"}
"""Shared with the worker consumer (steps 4-6) — redeclaring a queue with mismatched arguments fails."""


async def publish_generate_audio_job(
    *,
    settings: RabbitMq,
    body: dict[str, Any],
    headers: dict[str, Any],
) -> None:
    """Publish one job message to the configured quorum queue."""

    connection = await aio_pika.connect_robust(settings.connection_string)

    try:
        channel = await connection.channel()
        queue = await channel.declare_queue(
            settings.queue_name,
            durable=True,
            arguments=QUEUE_ARGUMENTS,
        )
        message = aio_pika.Message(
            body=json.dumps(body).encode("utf-8"),
            headers=headers,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await channel.default_exchange.publish(message, routing_key=queue.name)
    finally:
        await connection.close()
