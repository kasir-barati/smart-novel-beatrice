from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient
from testcontainers.core.container import DockerContainer
from testcontainers.core.image import DockerImage
from testcontainers.core.waiting_utils import wait_for_logs


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTAINER_PORT = 3000
HOST_OLLAMA_URL_FROM_HOST = "http://localhost:11434"
HOST_OLLAMA_URL_FROM_CONTAINER = "http://host.docker.internal:11434/v1"


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


def _ollama_is_reachable() -> bool:
    try:
        return httpx.get(f"{HOST_OLLAMA_URL_FROM_HOST}/api/tags", timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture(scope="session")
def require_live_ollama() -> None:
    """Skip the whole live_llm test module if Ollama isn't reachable on the host."""

    if not _ollama_is_reachable():
        pytest.skip(
            "Live Ollama not reachable at http://localhost:11434. "
            "Start it with `docker compose up -d ollama`.",
            allow_module_level=True,
        )


@pytest.fixture(scope="session")
def live_app_container(
    app_image: str,
    require_live_ollama: None,
) -> Iterator[DockerContainer]:
    """Start the app container talking to the host's real Ollama."""

    container = (
        DockerContainer(app_image)
        .with_exposed_ports(CONTAINER_PORT)
        .with_env("LLM__BASE_URL", HOST_OLLAMA_URL_FROM_CONTAINER)
        .with_env("LLM__MODEL", "llama3.2:1b")
        .with_env("LLM__TIMEOUT_MS", "180000")
        .with_env("OTEL__ENABLED", "false")
        .with_env("PORT", str(CONTAINER_PORT))
        .with_kwargs(extra_hosts={"host.docker.internal": "host-gateway"})
    )

    container.start()

    try:
        wait_for_logs(container, r"Uvicorn running on", timeout=60)
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def live_app_base_url(live_app_container: DockerContainer) -> str:
    host = live_app_container.get_container_host_ip()
    port = live_app_container.get_exposed_port(CONTAINER_PORT)

    return f"http://{host}:{port}"


@pytest_asyncio.fixture
async def live_http_client(live_app_base_url: str) -> AsyncIterator[AsyncClient]:
    """Yield an ``httpx.AsyncClient`` bound to the live-LLM-backed app container."""

    async with AsyncClient(base_url=live_app_base_url, timeout=240.0) as client:
        yield client
