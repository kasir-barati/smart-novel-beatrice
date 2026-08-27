"""
Integration test for the ``audioVoices`` GraphQL query.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.wiremock import WireMockClient


pytestmark = pytest.mark.asyncio


AUDIO_VOICES_QUERY = """
    query AudioVoices {
        audioVoices
    }
"""


async def test_audio_voices_returns_configured_provider_voice_names(
    http_client: AsyncClient, wiremock: WireMockClient
) -> None:
    wiremock.stub(
        "GET",
        "/v1/voices",
        status=200,
        json_body={"voices": [{"name": "qwen-voice-a"}, {"name": "qwen-voice-b"}]},
    )

    response = await http_client.post("/graphql", json={"query": AUDIO_VOICES_QUERY})

    assert response.status_code == 200
    body = response.json()
    assert body.get("errors") is None, body
    assert body["data"]["audioVoices"] == ["qwen-voice-a", "qwen-voice-b"]
