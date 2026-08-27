from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from src.utils import LoggingMode, LogLevel, Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_when_environment_is_empty(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    for key in list(os.environ):
        if key.startswith(
            (
                "LLM__",
                "OTEL__",
                "LOGGING__",
                "EXPLAIN_WORD__",
                "NORMALIZE_TTS__",
            )
        ) or key in {
            "PORT",
            "SERVICE_NAME",
        }:
            monkeypatch.delenv(key, raising=False)

    result = Settings()

    assert result.port == 3000
    assert result.logging.mode is LoggingMode.JSON
    assert result.logging.level is LogLevel.INFO
    assert result.service_name == "beatrice"
    assert result.llm.base_url == "http://ollama:11434/v1"
    assert result.llm.model == "qwen2.5:3b"
    assert result.explain_word.model is None
    assert result.otel.enabled is False


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PORT", "4242")
    monkeypatch.setenv("LOGGING__MODE", "PLAIN_TEXT")
    monkeypatch.setenv("LOGGING__LEVEL", "debug")
    monkeypatch.setenv("LLM__MODEL", "qwen2.5:7b")
    monkeypatch.setenv("EXPLAIN_WORD__TEMPERATURE", "0.4")

    result = Settings()

    assert result.port == 4242
    assert result.logging.mode is LoggingMode.PLAIN_TEXT
    assert result.logging.level is LogLevel.DEBUG
    assert result.llm.model == "qwen2.5:7b"
    assert result.explain_word.temperature == pytest.approx(0.4)


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PORT", "5000")
    first = get_settings()
    monkeypatch.setenv("PORT", "6000")  # would change output if we re-instantiated

    result = get_settings()

    assert first is result
    assert first.port == 5000
    assert result.port == 5000
