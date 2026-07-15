from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest

from src.modules.normalize_tts.resolver import normalize_text_for_tts
from src.modules.normalize_tts.types import NormalizedText
from src.utils import LlmError, NonEmptyTrimmedString, get_settings
from src.utils.exceptions import LLM_ERROR_CODE


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_normalize_tts_response(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "src.modules.normalize_tts.resolver.normalize_tts_via_agent",
        AsyncMock(
            return_value=NormalizedText(normalized_text="wh... what are you doing here?"),
        ),
    )

    result = await normalize_text_for_tts(NonEmptyTrimmedString("W-What are you doing here?"))

    assert result == "wh... what are you doing here?"


async def test_llm_error_is_wrapped_and_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "src.modules.normalize_tts.resolver.normalize_tts_via_agent",
        AsyncMock(side_effect=RuntimeError("upstream boom")),
    )

    with caplog.at_level("WARNING"), pytest.raises(LlmError) as excinfo:
        await normalize_text_for_tts(NonEmptyTrimmedString("hi there"))

    assert excinfo.value.code == LLM_ERROR_CODE
    assert "upstream boom" not in excinfo.value.message
    joined_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "TTS normalization" in joined_logs
    detail_captured = any("RuntimeError" in str(r.exc_info) for r in caplog.records if r.exc_info)
    assert detail_captured
