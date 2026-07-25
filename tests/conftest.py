"""
Session-wide fixtures for the integration test suite.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

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
OTEL_COLLECTOR_IMAGE = "otel/opentelemetry-collector-contrib:0.110.0"
OTEL_COLLECTOR_ALIAS = "otel-collector"
OTEL_COLLECTOR_CONFIG = Path(__file__).resolve().parent / "fixtures" / "otel-collector-config.yaml"


def _ensure_ollama_image_exists() -> None:
    """
    Build ``smart-novel-beatrice-ollama:latest`` if it isn't already loaded.
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
    """
    Shared Docker network so the app can reach Ollama by alias.
    """

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
def otel_export_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Host-side directory the collector writes exported spans to."""

    export_dir = tmp_path_factory.mktemp("otel-export")
    # World-writable so the collector container (any UID) can create the file.
    export_dir.chmod(0o777)
    return export_dir


@pytest.fixture(scope="session")
def otel_collector_container(
    docker_network: Network,
    otel_export_dir: Path,
) -> Iterator[DockerContainer]:
    """
    Start an OTel collector on the shared network with a file exporter.
    """

    container = (
        DockerContainer(OTEL_COLLECTOR_IMAGE)
        .with_command("--config=/etc/otel-collector-config.yaml")
        .with_network(docker_network)
        .with_network_aliases(OTEL_COLLECTOR_ALIAS)
        .with_volume_mapping(str(OTEL_COLLECTOR_CONFIG), "/etc/otel-collector-config.yaml", "ro")
        .with_volume_mapping(str(otel_export_dir), "/export", "rw")
        .with_kwargs(user=f"{os.getuid()}:{os.getgid()}")
        .waiting_for(LogMessageWaitStrategy("Everything is ready").with_startup_timeout(30))
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
    otel_collector_container: DockerContainer,
) -> Iterator[DockerContainer]:
    """
    Start the beatrice container on the shared network with Ollama + collector.
    """

    container = (
        DockerContainer(app_image)
        .with_exposed_ports(CONTAINER_PORT)
        .with_network(docker_network)
        .with_env("LLM__BASE_URL", f"http://{OLLAMA_NETWORK_ALIAS}:11434/v1")
        .with_env("LLM__MODEL", OLLAMA_MODEL)
        .with_env("LLM__TIMEOUT_MS", "180000")
        .with_env("OTEL__ENABLED", "true")
        .with_env("OTEL__EXPORTER_OTLP_ENDPOINT", f"http://{OTEL_COLLECTOR_ALIAS}:4318")
        .with_env("OTEL__TRACES_SAMPLER", "parentbased_always_on")
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


# ---------------------------------------------------------------------------
# OTel span reader
# ---------------------------------------------------------------------------


SpanDict = dict[str, Any]
SpansReader = Callable[[], list[SpanDict]]


@pytest.fixture
def otel_spans_reader(otel_export_dir: Path) -> Iterator[SpansReader]:
    """
    Return a callable that reads and flattens the collector's exported spans.
    """

    export_file = otel_export_dir / "spans.jsonl"
    start_offset = export_file.stat().st_size if export_file.exists() else 0

    def _read() -> list[SpanDict]:
        if not export_file.exists():
            return []

        with export_file.open("rb") as fh:
            fh.seek(start_offset)
            payload = fh.read()

        spans: list[SpanDict] = []

        for raw_line in payload.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError:
                continue

            for resource_spans in envelope.get("resourceSpans", ()):
                resource_attrs = _kv_list_to_dict(
                    resource_spans.get("resource", {}).get("attributes", ())
                )
                for scope_spans in resource_spans.get("scopeSpans", ()):
                    for span in scope_spans.get("spans", ()):
                        spans.append(
                            {
                                "name": span.get("name"),
                                "attributes": _kv_list_to_dict(span.get("attributes", ())),
                                "resource": resource_attrs,
                                "start_ns": _to_int(span.get("startTimeUnixNano")),
                                "end_ns": _to_int(span.get("endTimeUnixNano")),
                            }
                        )
        return spans

    yield _read


def _kv_list_to_dict(kv_list: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Convert an OTLP-JSON ``KeyValue[]`` list into a plain dict.
    """

    out: dict[str, Any] = {}
    for entry in kv_list:
        key = entry.get("key")
        if key is None:
            continue
        value = entry.get("value", {})

        if "stringValue" in value:
            out[key] = value["stringValue"]
        elif "intValue" in value:
            out[key] = _to_int(value["intValue"])
        elif "doubleValue" in value:
            out[key] = float(value["doubleValue"])
        elif "boolValue" in value:
            out[key] = bool(value["boolValue"])
        elif "arrayValue" in value:
            out[key] = [_unwrap_value(item) for item in value["arrayValue"].get("values", ())]

    return out


def _unwrap_value(value: dict[str, Any]) -> Any:
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        return _to_int(value["intValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "boolValue" in value:
        return bool(value["boolValue"])
    return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
