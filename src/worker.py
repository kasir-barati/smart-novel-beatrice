"""Worker process entry point — consumes `generateAudio` jobs from RabbitMQ."""

from __future__ import annotations

import asyncio
import logging
from importlib.metadata import version

from src.modules.audio import run_worker
from src.utils import get_settings, setup_observability


_logger = logging.getLogger(__name__)


def main() -> None:
    """Entry point for ``python -m src.worker`` / ``python src/worker.py``."""

    settings = get_settings()
    setup_observability(settings, version=version(settings.app_name))

    _logger.info(
        "%s worker ready",
        settings.service_name,
        extra={"service_name": settings.service_name, "queue_name": settings.rabbitmq.queue_name},
    )

    asyncio.run(run_worker(settings))


if __name__ == "__main__":
    main()
