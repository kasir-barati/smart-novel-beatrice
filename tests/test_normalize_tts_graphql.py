"""
Integration tests for the ``normalizeTextForTts`` GraphQL mutation.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.fixtures import LONG_STORY_CHUNKS, SpansReader, find_spans_with_attribute, wait_for_spans


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


@pytest.mark.integration
async def test_chunked_long_story_emits_gen_ai_token_metrics(
    http_client: AsyncClient,
    otel_spans_reader: SpansReader,
) -> None:
    # Arrange
    user_id = "test-user-long-story"
    normalised_chunks: list[str] = []
    chunk_count = len(LONG_STORY_CHUNKS)

    # Act
    for index, chunk in enumerate(LONG_STORY_CHUNKS):
        response = await http_client.post(
            "/graphql",
            headers={"x-app-user-id": user_id},
            json={
                "query": NORMALIZE_TTS_MUTATION,
                "variables": {"text": chunk},
            },
        )
        assert response.status_code == 200, (index, response.text)
        body = response.json()
        assert body.get("errors") is None, (index, body)
        payload = body["data"]["normalizeTextForTts"]
        assert isinstance(payload, str) and payload.strip(), (index, payload)
        normalised_chunks.append(payload)
        print(f"\n--- chunk {index} (input {len(chunk)} chars → output {len(payload)} chars) ---")
        print("INPUT :", chunk)
        print("OUTPUT:", payload)

    # Assert
    spans = wait_for_spans(
        otel_spans_reader,
        lambda captured: (
            len([s for s in captured if s["attributes"].get("enduser.id") == user_id])
            >= chunk_count
            and len(find_spans_with_attribute(captured, attribute="gen_ai.usage.input_tokens"))
            >= chunk_count
        ),
        timeout_s=15.0,
    )
    token_spans = find_spans_with_attribute(spans, attribute="gen_ai.usage.input_tokens")
    assert (
        len(token_spans) >= chunk_count
    ), f"expected at least one model-request span per chunk ({chunk_count}), got {len(token_spans)}"
    _assert_token_usage_attributes(token_spans)
    _assert_spans_have_enduser_id(spans, user_id=user_id, chunk_count=chunk_count)
    _assert_prompt_template_metadata(spans, template_name="normalize_tts")


def _assert_token_usage_attributes(token_spans: list[dict]) -> None:
    total_input = 0
    total_output = 0

    for span in token_spans:
        attrs = span["attributes"]
        input_tokens = attrs.get("gen_ai.usage.input_tokens")
        output_tokens = attrs.get("gen_ai.usage.output_tokens")

        assert isinstance(input_tokens, int) and input_tokens > 0, attrs
        assert isinstance(output_tokens, int) and output_tokens > 0, attrs

        total_input += input_tokens
        total_output += output_tokens

        assert attrs.get("gen_ai.provider.name") is not None, attrs
        assert attrs.get("gen_ai.request.model") is not None, attrs

    print(
        f"\n--- token totals across {len(token_spans)} model requests: "
        f"input={total_input}, output={total_output} ---"
    )


def _assert_prompt_template_metadata(spans: list[dict], *, template_name: str) -> None:
    print("\n--- ALL CAPTURED SPANS (name → attributes) ---")

    for span in spans:
        print(f"  name={span['name']!r}")

        for key, value in sorted(span["attributes"].items()):
            rendered = repr(value)

            if len(rendered) > 200:
                rendered = rendered[:200] + "..."

            print(f"    {key} = {rendered}")

    matching = [span for span in spans if _span_carries_prompt_template(span, template_name)]

    assert (
        matching
    ), f"expected at least one span carrying the {template_name!r} prompt-template metadata"


def _span_carries_prompt_template(span: dict, template_name: str) -> bool:
    attrs = span["attributes"]

    for key in ("metadata.prompt.template.name", "prompt.template.name"):
        if attrs.get(key) == template_name:
            return True

    raw = attrs.get("metadata")
    return isinstance(raw, str) and "prompt.template.name" in raw and template_name in raw


def _assert_spans_have_enduser_id(spans: list[dict], *, user_id: str, chunk_count: int) -> None:
    enduser_spans = [span for span in spans if span["attributes"].get("enduser.id") == user_id]

    assert (
        len(enduser_spans) >= chunk_count
    ), f"expected at least {chunk_count} spans tagged with enduser.id={user_id!r}, saw {len(enduser_spans)}"
