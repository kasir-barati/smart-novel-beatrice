"""
Session-wide fixtures for the integration test suite.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import docker
import docker.errors
import pytest
import pytest_asyncio
from httpx import AsyncClient
from testcontainers.core.container import DockerContainer
from testcontainers.core.image import DockerImage
from testcontainers.core.network import Network
from testcontainers.core.wait_strategies import LogMessageWaitStrategy
from testcontainers.ollama import OllamaContainer


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTAINER_PORT = 3000
OLLAMA_MODEL = "qwen2.5:3b"
OLLAMA_IMAGE = "smart-novel-beatrice-ollama:latest"
OLLAMA_CONTEXT = PROJECT_ROOT / "local-setup" / "ollama"
OLLAMA_NETWORK_ALIAS = "ollama"


def _ensure_ollama_image_exists() -> None:
    """
    Build ``smart-novel-beatrice-ollama:latest`` if it isn't already loaded.

    In CI the image is built by a dedicated workflow step (with GHA caching) before pytest runs, so this is typically a no-op. Locally, first-time
    contributors get a transparent build.
    """

    client = docker.from_env()
    try:
        client.images.get(OLLAMA_IMAGE)
        return
    except docker.errors.ImageNotFound:
        pass

    image = DockerImage(
        path=str(OLLAMA_CONTEXT),
        tag=OLLAMA_IMAGE,
        buildargs={"OLLAMA_MODEL": OLLAMA_MODEL},
    )
    image.build()


@pytest.fixture(scope="session")
def docker_network() -> Iterator[Network]:
    """Shared Docker network so the app can reach Ollama by alias."""

    with Network() as network:
        yield network


@pytest.fixture(scope="session")
def ollama_container(docker_network: Network) -> Iterator[OllamaContainer]:
    """
    Start Ollama on the shared network with the pre-baked model image.
    """

    _ensure_ollama_image_exists()

    container = (
        OllamaContainer(image=OLLAMA_IMAGE)
        .with_network(docker_network)
        .with_network_aliases(OLLAMA_NETWORK_ALIAS)
    )

    with container:
        yield container


@pytest.fixture(scope="session")
def app_image() -> str:
    """Build the beatrice Docker image once per test session."""

    image = DockerImage(path=str(PROJECT_ROOT), tag="smart-novel-beatrice:test")
    image.build()
    return str(image)


@pytest.fixture(scope="session")
def app_container(
    app_image: str,
    docker_network: Network,
    ollama_container: OllamaContainer,
) -> Iterator[DockerContainer]:
    """
    Start the beatrice container on the shared network with Ollama.
    """

    container = (
        DockerContainer(app_image)
        .with_exposed_ports(CONTAINER_PORT)
        .with_network(docker_network)
        .with_env("LLM__BASE_URL", f"http://{OLLAMA_NETWORK_ALIAS}:11434/v1")
        .with_env("LLM__MODEL", OLLAMA_MODEL)
        .with_env("LLM__TIMEOUT_MS", "180000")
        .with_env("OTEL__ENABLED", "false")
        .with_env("PORT", str(CONTAINER_PORT))
        .waiting_for(LogMessageWaitStrategy("Uvicorn running on").with_startup_timeout(60))
    )

    container.start()

    try:
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
    """
    Yield an ``httpx.AsyncClient`` bound to the beatrice container.
    """

    async with AsyncClient(base_url=app_base_url, timeout=240.0) as client:
        yield client
