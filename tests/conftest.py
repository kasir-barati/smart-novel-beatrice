from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from testcontainers.core.container import DockerContainer
from testcontainers.core.image import DockerImage
from testcontainers.core.waiting_utils import wait_for_logs


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTAINER_PORT = 3000


def _build_image() -> str:
    """Build the app image using Dockerfile and return the tag."""
    image = DockerImage(path=str(PROJECT_ROOT), tag="smart-novel-beatrice:test")
    image.build()

    return str(image)


@pytest.fixture(scope="session")
def app_image() -> str:
    """Build the Docker image once per test session."""

    return _build_image()


@pytest.fixture(scope="session")
def app_container(app_image: str) -> Iterator[DockerContainer]:
    """Start the app container once per test session."""

    container = (
        DockerContainer(app_image)
        .with_exposed_ports(CONTAINER_PORT)
        .with_env("LLM__MODEL", "integration-model")
        .with_env("OTEL__ENABLED", "false")
        .with_env("PORT", str(CONTAINER_PORT))
    )

    container.start()

    try:
        wait_for_logs(container, r"Uvicorn running on", timeout=60)
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def app_base_url(app_container: DockerContainer) -> str:
    host = app_container.get_container_host_ip()
    port = app_container.get_exposed_port(CONTAINER_PORT)

    return f"http://{host}:{port}"


@pytest_asyncio.fixture
async def http_client(app_base_url: str) -> AsyncIterator[AsyncClient]:
    """Yield an ``httpx.AsyncClient`` bound to the containerized app."""

    async with AsyncClient(base_url=app_base_url) as client:
        yield client
