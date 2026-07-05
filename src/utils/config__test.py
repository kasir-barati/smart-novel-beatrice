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

    settings = Settings()

    assert settings.port == 3000
    assert settings.logging.mode is LoggingMode.JSON
    assert settings.logging.level is LogLevel.INFO
    assert settings.service_name == "beatrice"
    assert settings.llm.base_url == "http://ollama:11434/v1"
    assert settings.llm.model == "llama3.2:1b"
    assert settings.explain_word.model is None
    assert settings.otel.enabled is False


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PORT", "4242")
    monkeypatch.setenv("LOGGING__MODE", "PLAIN_TEXT")
    monkeypatch.setenv("LOGGING__LEVEL", "debug")
    monkeypatch.setenv("LLM__MODEL", "qwen2.5:7b")
    monkeypatch.setenv("EXPLAIN_WORD__TEMPERATURE", "0.4")

    settings = Settings()

    assert settings.port == 4242
    assert settings.logging.mode is LoggingMode.PLAIN_TEXT
    assert settings.logging.level is LogLevel.DEBUG
    assert settings.llm.model == "qwen2.5:7b"
    assert settings.explain_word.temperature == pytest.approx(0.4)


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PORT", "5000")

    first = get_settings()
    monkeypatch.setenv("PORT", "6000")  # would change output if we re-instantiated
    second = get_settings()

    assert first is second
    assert first.port == 5000
    assert second.port == 5000
