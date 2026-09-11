"""
Integration test for the ``generateAudio`` GraphQL mutation.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import aio_pika
import pytest
from httpx import AsyncClient
from minio import Minio
from minio.error import S3Error
from testcontainers.core.container import DockerContainer

from tests.wiremock import WireMockClient


pytestmark = pytest.mark.asyncio


GENERATE_AUDIO_MUTATION = """
    mutation GenerateAudio(
        $text: String!
        $voice: String!
        $genUploadUrl: String!
        $statusCallbackUrl: String!
        $instruct: String
    ) {
        generateAudio(
            text: $text
            voice: $voice
            genUploadUrl: $genUploadUrl
            statusCallbackUrl: $statusCallbackUrl
            instruct: $instruct
        ) {
            jobId
        }
    }
"""


_SYNTHESIZE_PATH = "/api/v1/services/aigc/multimodal-generation/generation"


def _stub_synthesize(
    wiremock: WireMockClient, wiremock_internal_url: str, *, audio_bytes: bytes, audio_path: str
) -> None:
    """
    DashScope's synthesize endpoint returns a JSON body carrying a URL, not the audio
    itself — stub both hops: the initial POST, and the follow-up GET the provider
    makes to actually download the audio.
    """

    wiremock.stub(
        "POST",
        _SYNTHESIZE_PATH,
        status=200,
        json_body={"output": {"audio": {"url": f"{wiremock_internal_url}{audio_path}"}}},
    )
    wiremock.stub("GET", audio_path, status=200, body_bytes=audio_bytes)


def _variables(**overrides: str) -> dict[str, str]:
    base = {
        "text": "hello world",
        "voice": "qwen-voice-a",
        "genUploadUrl": "http://wiremock:8080/upload",
        "statusCallbackUrl": "http://wiremock:8080/status-callback",
    }
    base.update(overrides)
    return base


async def test_generate_audio_returns_202_and_publishes_to_the_queue(
    http_client: AsyncClient,
    wiremock: WireMockClient,
    rabbitmq_host_url: str,
) -> None:
    wiremock.stub("POST", "/status-callback", status=200, json_body={"ok": True})

    response = await http_client.post(
        "/graphql", json={"query": GENERATE_AUDIO_MUTATION, "variables": _variables()}
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body.get("errors") is None, body
    job_id = body["data"]["generateAudio"]["jobId"]
    assert job_id

    connection = await aio_pika.connect_robust(rabbitmq_host_url)
    try:
        channel = await connection.channel()
        queue = await channel.declare_queue(
            "beatrice.generate_audio", durable=True, arguments={"x-queue-type": "quorum"}
        )
        incoming = await queue.get(timeout=10)
        assert incoming is not None
        payload = json.loads(incoming.body)
        await incoming.ack()
    finally:
        await connection.close()

    assert payload == {
        "jobId": job_id,
        "text": "hello world",
        "voice": "qwen-voice-a",
        "genUploadUrl": "http://wiremock:8080/upload",
        "statusCallbackUrl": "http://wiremock:8080/status-callback",
    }
    assert "timestamp" in incoming.headers

    queued_requests = wiremock.requests_for("/status-callback")
    assert len(queued_requests) == 1
    assert json.loads(queued_requests[0]["body"]) == {"status": "queued", "jobId": job_id}


async def test_generate_audio_publishes_instruct_when_given(
    http_client: AsyncClient,
    wiremock: WireMockClient,
    rabbitmq_host_url: str,
) -> None:
    """
    app_container (tests/conftest.py) defaults TTS__DEFAULT_PROVIDER to Qwen3-TTS, so
    this only exercises the accept-and-publish path. The reject-when-Gemini path needs
    a differently-configured app instance and is covered at the unit tier instead
    (src/modules/audio/resolver__test.py::test_generate_audio_rejects_instruct_when_provider_is_not_qwen).
    """

    wiremock.stub("POST", "/status-callback", status=200, json_body={"ok": True})

    response = await http_client.post(
        "/graphql",
        json={
            "query": GENERATE_AUDIO_MUTATION,
            "variables": _variables(instruct="speak in a whisper"),
        },
    )

    assert response.status_code == 202, response.text
    job_id = response.json()["data"]["generateAudio"]["jobId"]

    connection = await aio_pika.connect_robust(rabbitmq_host_url)
    try:
        channel = await connection.channel()
        queue = await channel.declare_queue(
            "beatrice.generate_audio", durable=True, arguments={"x-queue-type": "quorum"}
        )
        incoming = await queue.get(timeout=10)
        assert incoming is not None
        payload = json.loads(incoming.body)
        await incoming.ack()
    finally:
        await connection.close()

    assert payload["jobId"] == job_id
    assert payload["instruct"] == "speak in a whisper"


async def test_generate_audio_rejects_oversized_text(
    http_client: AsyncClient, wiremock: WireMockClient
) -> None:
    response = await http_client.post(
        "/graphql",
        json={
            "query": GENERATE_AUDIO_MUTATION,
            "variables": _variables(text="a" * 5000),
        },
    )

    body = response.json()
    assert body["errors"], body
    assert "at most" in body["errors"][0]["message"]


async def test_generate_audio_rejects_a_callback_host_not_on_the_allow_list(
    http_client: AsyncClient, wiremock: WireMockClient
) -> None:
    response = await http_client.post(
        "/graphql",
        json={
            "query": GENERATE_AUDIO_MUTATION,
            "variables": _variables(genUploadUrl="http://evil.example.com/upload"),
        },
    )

    body = response.json()
    assert body["errors"], body
    assert "allow-list" in body["errors"][0]["message"]


async def test_generate_audio_pipeline_uploads_the_file_and_reports_completion(
    http_client: AsyncClient,
    wiremock: WireMockClient,
    wiremock_internal_url: str,
    worker_container: DockerContainer,
    minio_verify_client: Minio,
    minio_bucket: str,
    presigned_upload_url_factory: Callable[[str], str],
) -> None:
    """
    Drives a job end-to-end through steps 3-5: generateAudio publishes it, the worker
    consumes it, synthesizes against a stubbed provider, and uploads to a real MinIO
    presigned URL obtained through a stubbed genUploadUrl.
    """

    audio_bytes = b"fake-audio-bytes-from-the-stubbed-provider"
    _stub_synthesize(
        wiremock,
        wiremock_internal_url,
        audio_bytes=audio_bytes,
        audio_path="/files/pipeline-test.wav",
    )
    object_name = "pipeline-test.mp3"
    presigned_url = presigned_upload_url_factory(object_name)
    wiremock.stub("POST", "/upload", status=200, json_body={"url": presigned_url})
    wiremock.stub("POST", "/status-callback", status=200, json_body={"ok": True})

    response = await http_client.post(
        "/graphql", json={"query": GENERATE_AUDIO_MUTATION, "variables": _variables()}
    )

    assert response.status_code == 202, response.text
    job_id = response.json()["data"]["generateAudio"]["jobId"]

    stat = await _wait_for_object(minio_verify_client, minio_bucket, object_name)

    assert stat.size == len(audio_bytes)
    assert minio_verify_client.get_object(minio_bucket, object_name).read() == audio_bytes

    status_updates = [json.loads(r["body"]) for r in wiremock.requests_for("/status-callback")]
    completed = next(u for u in status_updates if u.get("status") == "completed")
    assert completed == {"status": "completed", "fileSizeBytes": len(audio_bytes), "jobId": job_id}
    statuses_seen = [u["status"] for u in status_updates]
    assert statuses_seen == ["queued", "generating", "uploading", "completed"]
    assert all(u["jobId"] == job_id for u in status_updates)


async def test_generate_audio_pipeline_forwards_instruct_to_the_provider(
    http_client: AsyncClient,
    wiremock: WireMockClient,
    wiremock_internal_url: str,
    worker_container: DockerContainer,
    minio_verify_client: Minio,
    minio_bucket: str,
    presigned_upload_url_factory: Callable[[str], str],
) -> None:
    """Same pipeline as above, but asserting instruct reaches the provider's request body."""

    audio_bytes = b"fake-audio-bytes-from-the-stubbed-provider"
    _stub_synthesize(
        wiremock,
        wiremock_internal_url,
        audio_bytes=audio_bytes,
        audio_path="/files/pipeline-instruct-test.wav",
    )
    object_name = "pipeline-instruct-test.mp3"
    presigned_url = presigned_upload_url_factory(object_name)
    wiremock.stub("POST", "/upload", status=200, json_body={"url": presigned_url})
    wiremock.stub("POST", "/status-callback", status=200, json_body={"ok": True})

    response = await http_client.post(
        "/graphql",
        json={
            "query": GENERATE_AUDIO_MUTATION,
            "variables": _variables(instruct="speak in a whisper"),
        },
    )

    assert response.status_code == 202, response.text

    await _wait_for_object(minio_verify_client, minio_bucket, object_name)

    synthesize_requests = wiremock.requests_for(_SYNTHESIZE_PATH)
    assert len(synthesize_requests) == 1
    assert json.loads(synthesize_requests[0]["body"])["instructions"] == "speak in a whisper"


async def _wait_for_object(client: Minio, bucket: str, object_name: str, timeout: float = 20.0):
    """Poll MinIO for an object the worker uploads asynchronously, out-of-band."""

    deadline = asyncio.get_event_loop().time() + timeout

    while True:
        try:
            return client.stat_object(bucket, object_name)
        except S3Error:
            if asyncio.get_event_loop().time() >= deadline:
                raise
            await asyncio.sleep(0.5)


async def _poll_for_message(
    queue: aio_pika.abc.AbstractQueue, *, timeout: float
) -> aio_pika.abc.AbstractIncomingMessage:
    """
    `Queue.get()` is a single, non-blocking poll — passing `timeout` only bounds that
    one RPC call, not how long to wait for a message to arrive — so a delayed publish
    (a retry, here) needs its own poll loop rather than a single `get()`.
    """

    deadline = asyncio.get_event_loop().time() + timeout

    while True:
        message = await queue.get(fail=False, timeout=5)
        if message is not None:
            return message
        if asyncio.get_event_loop().time() >= deadline:
            raise TimeoutError(f"No message on {queue.name!r} within {timeout}s")
        await asyncio.sleep(0.5)


async def test_generate_audio_exhausts_retries_and_lands_on_the_dlq(
    http_client: AsyncClient,
    wiremock: WireMockClient,
    worker_container: DockerContainer,
    rabbitmq_host_url: str,
) -> None:
    """
    worker_container is configured (see tests/conftest.py) with a delivery limit of 2
    and a 1s retry delay, so a synthesis call that always 500s should be retried once
    and then dead-lettered.
    """

    wiremock.stub("POST", _SYNTHESIZE_PATH, status=500)
    wiremock.stub("POST", "/status-callback", status=200, json_body={"ok": True})

    response = await http_client.post(
        "/graphql", json={"query": GENERATE_AUDIO_MUTATION, "variables": _variables()}
    )

    assert response.status_code == 202, response.text
    job_id = response.json()["data"]["generateAudio"]["jobId"]

    connection = await aio_pika.connect_robust(rabbitmq_host_url)
    try:
        channel = await connection.channel()
        dlq = await channel.declare_queue(
            "beatrice.generate_audio.dlq", durable=True, arguments={"x-queue-type": "quorum"}
        )
        incoming = await _poll_for_message(dlq, timeout=15)
        payload = json.loads(incoming.body)
        await incoming.ack()
    finally:
        await connection.close()

    assert payload["text"] == "hello world"
    assert incoming.headers["x-attempt"] == 2

    status_updates = [json.loads(r["body"]) for r in wiremock.requests_for("/status-callback")]
    failed_updates = [u for u in status_updates if u.get("status") == "failed"]
    assert len(failed_updates) == 2
    assert all(u["error"]["code"] == "TTS_PROVIDER_ERROR" for u in failed_updates)
    assert all(u["jobId"] == job_id for u in failed_updates)
