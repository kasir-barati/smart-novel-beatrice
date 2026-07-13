"""
E2E test for the ``explainWord`` GraphQL mutation.

Slow (~2 min on CPU); marked ``live_llm`` and skipped unless explicitly opted into with::

    uv run pytest tests/test_explain_word_graphql.py -m live_llm -v

Requires ``docker compose up -d ollama`` to be running so that ``http://localhost:11434`` responds. The test skips itself otherwise.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


pytestmark = [pytest.mark.asyncio, pytest.mark.live_llm]


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


async def test_explain_word_returns_structured_payload_from_live_ollama(
    live_http_client: AsyncClient,
) -> None:
    response = await live_http_client.post(
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
    assert isinstance(payload["meaning"], str) and payload["meaning"]
    assert isinstance(payload["simplifiedExplanation"], str) and payload["simplifiedExplanation"]
    assert isinstance(payload["synonyms"], list)
    assert isinstance(payload["antonyms"], list)
    # Sanity: the model shouldn't return the input word among its own synonyms.
    assert "ephemeral" not in [s.lower() for s in payload["synonyms"]]
