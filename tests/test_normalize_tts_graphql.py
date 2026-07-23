"""
Integration tests for the ``normalizeTextForTts`` GraphQL mutation.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


NORMALIZE_TTS_MUTATION = """
    mutation NormalizeTts($text: String!) {
        normalizeTextForTts(text: $text)
    }
"""


async def test_normalize_text_for_tts_returns_string(
    http_client: AsyncClient,
) -> None:
    """
    The pipeline returns EITHER a normalised string
    """

    response = await http_client.post(
        "/graphql",
        json={
            "query": NORMALIZE_TTS_MUTATION,
            "variables": {
                "text": "W-What are you doing? BOOM! ahhhh~",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    payload = body["data"]["normalizeTextForTts"]
    assert isinstance(payload, str)
    assert payload


async def test_empty_input_is_rejected(http_client: AsyncClient) -> None:
    """Whitespace-only input is rejected before reaching the LLM."""

    response = await http_client.post(
        "/graphql",
        json={
            "query": NORMALIZE_TTS_MUTATION,
            "variables": {"text": "   "},
        },
    )

    body = response.json()
    assert body["errors"], body
    message = body["errors"][0]["message"]
    assert "text" in message
    assert "at least 1 character" in message


async def test_input_over_max_length_is_rejected(http_client: AsyncClient) -> None:
    """Input longer than the 4000-char cap is rejected before reaching the LLM."""

    response = await http_client.post(
        "/graphql",
        json={
            "query": NORMALIZE_TTS_MUTATION,
            "variables": {"text": "a" * 4001},
        },
    )

    body = response.json()
    assert body["errors"], body
    message = body["errors"][0]["message"]
    assert "text" in message
    assert "at most 4000 characters" in message
