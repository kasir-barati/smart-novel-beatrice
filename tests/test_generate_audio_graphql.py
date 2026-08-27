"""
Integration test for the ``generateAudio`` GraphQL mutation.
"""

from __future__ import annotations

import json

import aio_pika
import pytest
from httpx import AsyncClient

from tests.wiremock import WireMockClient


pytestmark = pytest.mark.asyncio


GENERATE_AUDIO_MUTATION = """
    mutation GenerateAudio(
        $text: String!
        $voice: String!
        $genUploadUrl: String!
        $statusCallbackUrl: String!
    ) {
        generateAudio(
            text: $text
            voice: $voice
            genUploadUrl: $genUploadUrl
            statusCallbackUrl: $statusCallbackUrl
        ) {
            jobId
        }
    }
"""


def _stub_voices(wiremock: WireMockClient) -> None:
    wiremock.stub("GET", "/v1/voices", status=200, json_body={"voices": [{"name": "qwen-voice-a"}]})


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
    _stub_voices(wiremock)
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
    assert json.loads(queued_requests[0]["body"]) == {"status": "queued"}


async def test_generate_audio_rejects_oversized_text(
    http_client: AsyncClient, wiremock: WireMockClient
) -> None:
    _stub_voices(wiremock)

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
    _stub_voices(wiremock)

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
