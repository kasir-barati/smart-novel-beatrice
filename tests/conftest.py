"""
Session-wide fixtures for the integration test suite.
"""

from __future__ import annotations

import subprocess
import time
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
OLLAMA_READY_TIMEOUT_S = 180
OLLAMA_READY_POLL_INTERVAL_S = 2


def _ollama_is_reachable() -> bool:
    try:
        return httpx.get(f"{HOST_OLLAMA_URL_FROM_HOST}/api/tags", timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


def _wait_for_ollama(timeout_s: float) -> None:
    start = time.monotonic()

    while time.monotonic() - start < timeout_s:
        if _ollama_is_reachable():
            return
        time.sleep(OLLAMA_READY_POLL_INTERVAL_S)
    raise TimeoutError(
        f"Ollama did not become reachable at {HOST_OLLAMA_URL_FROM_HOST} within {timeout_s}s",
    )


@pytest.fixture(scope="session", autouse=True)
def docker_compose_ollama() -> Iterator[None]:
    """
    Boot the ollama compose service before the suite, stop it afterwards.
    """

    already_running = _ollama_is_reachable()
    if not already_running:
        subprocess.run(
            ["docker", "compose", "up", "-d", "--wait", "ollama"],
            cwd=PROJECT_ROOT,
            check=True,
        )
        _wait_for_ollama(OLLAMA_READY_TIMEOUT_S)

    try:
        yield
    finally:
        # Only stop what we started. Preserves developer workflow where Ollama was already up before invoking `make integration_test`.
        if not already_running:
            subprocess.run(
                ["docker", "compose", "stop", "ollama"],
                cwd=PROJECT_ROOT,
                check=False,
            )


@pytest.fixture(scope="session")
def app_image() -> str:
    """Build the beatrice Docker image once per test session."""

    image = DockerImage(path=str(PROJECT_ROOT), tag="smart-novel-beatrice:test")
    image.build()
    return str(image)


@pytest.fixture(scope="session")
def app_container(app_image: str) -> Iterator[DockerContainer]:
    """
    Start the beatrice container wired to the host-run Ollama.
    """

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
