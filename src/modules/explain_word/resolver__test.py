from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.modules.explain_word import resolver as resolver_module
from src.modules.explain_word.resolver import explain_word
from src.modules.explain_word.types import WordExplanation, WordExplanationType


async def test_explain_word_response(monkeypatch: pytest.MonkeyPatch) -> None:
    canned = WordExplanation(
        meaning="lasting a short time",
        simplified_explanation="not for long",
        synonyms=["fleeting", "brief", "momentary", "transitory", "passing"],
        antonyms=["permanent", "everlasting", "immortal", "abiding", "perpetual"],
    )
    fake_agent_call = AsyncMock(return_value=canned)
    monkeypatch.setattr(resolver_module, "explain_word_via_agent", fake_agent_call)

    projected = await explain_word("ephemeral", "The graffiti was ephemeral.")

    fake_agent_call.assert_awaited_once_with(
        word="ephemeral",
        context="The graffiti was ephemeral.",
    )
    assert isinstance(projected, WordExplanationType)
    assert projected.to_pydantic() == canned
