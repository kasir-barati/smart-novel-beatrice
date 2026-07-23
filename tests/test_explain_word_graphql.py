"""
Integration test for the ``explainWord`` GraphQL mutation.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


EXPLAIN_WORD_MUTATION = """
    mutation ExplainWord($word: String!, $context: String!) {
        explainWord(word: $word, context: $context) {
            meaning
            simplifiedExplanation
            synonyms
            antonyms
        }
    }
"""


async def test_explain_word_returns_wellformed_payload(http_client: AsyncClient) -> None:
    response = await http_client.post(
        "/graphql",
        json={
            "query": EXPLAIN_WORD_MUTATION,
            "variables": {
                "word": "ephemeral",
                "context": (
                    "The graffiti was ephemeral, washed away by the first rain of the season."
                ),
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body.get("errors") is None, body
    payload = body["data"]["explainWord"]
    assert isinstance(payload["meaning"], str)
    assert isinstance(payload["simplifiedExplanation"], str)
    assert isinstance(payload["synonyms"], list)
    assert isinstance(payload["antonyms"], list)
    assert all(isinstance(s, str) for s in payload["synonyms"])
    assert all(isinstance(a, str) for a in payload["antonyms"])


async def test_word_over_max_length_is_rejected(http_client: AsyncClient) -> None:
    response = await http_client.post(
        "/graphql",
        json={
            "query": EXPLAIN_WORD_MUTATION,
            "variables": {
                "word": "a" * 65,
                "context": "Some sentence containing the word.",
            },
        },
    )

    body = response.json()
    assert body["errors"], body
    message = body["errors"][0]["message"]
    assert "word" in message
    assert "at most 64 characters" in message


async def test_context_over_max_length_is_rejected(http_client: AsyncClient) -> None:
    response = await http_client.post(
        "/graphql",
        json={
            "query": EXPLAIN_WORD_MUTATION,
            "variables": {
                "word": "ephemeral",
                "context": "a" * 2001,
            },
        },
    )

    body = response.json()
    assert body["errors"], body
    message = body["errors"][0]["message"]
    assert "context" in message
    assert "at most 2000 characters" in message


async def test_empty_word_is_rejected(http_client: AsyncClient) -> None:
    response = await http_client.post(
        "/graphql",
        json={
            "query": EXPLAIN_WORD_MUTATION,
            "variables": {"word": "   ", "context": "Some sentence."},
        },
    )

    body = response.json()
    assert body["errors"], body
    message = body["errors"][0]["message"]
    assert "word" in message
    assert "at least 1 character" in message
