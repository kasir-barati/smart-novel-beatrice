from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.modules.explain_word import resolver as resolver_module
from src.modules.explain_word.resolver import explain_word
from src.modules.explain_word.types import WordExplanation, WordExplanationType
from src.utils import LLM_ERROR_CODE, LlmError, NonEmptyTrimmedString


async def test_explain_word_response(monkeypatch: pytest.MonkeyPatch) -> None:
    canned = WordExplanation(
        meaning="lasting a short time",
        simplified_explanation="not for long",
        synonyms=["fleeting", "brief", "momentary", "transitory", "passing"],
        antonyms=["permanent", "everlasting", "immortal", "abiding", "perpetual"],
    )
    fake_agent_call = AsyncMock(return_value=canned)
    monkeypatch.setattr(resolver_module, "explain_word_via_agent", fake_agent_call)

    projected = await explain_word(
        NonEmptyTrimmedString("ephemeral"),
        NonEmptyTrimmedString("The graffiti was ephemeral."),
    )

    fake_agent_call.assert_awaited_once_with(
        word="ephemeral",
        context="The graffiti was ephemeral.",
    )
    assert isinstance(projected, WordExplanationType)
    assert projected.to_pydantic() == canned


async def test_agent_failure_wraps_as_llm_exception(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        resolver_module,
        "explain_word_via_agent",
        AsyncMock(side_effect=RuntimeError("upstream boom")),
    )

    with caplog.at_level("WARNING"), pytest.raises(LlmError) as excinfo:
        await explain_word(
            NonEmptyTrimmedString("ephemeral"),
            NonEmptyTrimmedString("The graffiti was ephemeral."),
        )

    assert excinfo.value.code == LLM_ERROR_CODE
    assert "upstream boom" not in excinfo.value.message
    joined_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "explainWord" in joined_logs
    detail_captured = any("RuntimeError" in str(r.exc_info) for r in caplog.records if r.exc_info)
    assert detail_captured
