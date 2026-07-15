from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.settings import ModelSettings

from src.modules.explain_word.agent import build_agent, explain_word_via_agent
from src.modules.explain_word.types import WordExplanation
from src.utils import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _model_name_of(agent: object) -> str:
    """Extract model name & asserts the model is an OpenAI chat model"""

    model = getattr(agent, "model", None)

    assert isinstance(model, OpenAIChatModel)

    return model.model_name


def _model_settings_of(agent: object) -> ModelSettings:
    """Extract model settings as a plain dict"""
    settings = getattr(agent, "model_settings", None)

    assert isinstance(settings, dict), f"expected a dict, got {type(settings).__name__}"

    return cast(ModelSettings, settings)


def test_build_agent_prefers_endpoint_override_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXPLAIN_WORD__MODEL", "qwen2.5:7b")
    monkeypatch.setenv("LLM__MODEL", "qwen2.5:0.5b")

    agent = build_agent(Settings())

    assert _model_name_of(agent) == "qwen2.5:7b"


def test_build_agent_falls_back_to_global_model(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM__MODEL", "qwen2.5:0.5b")

    agent = build_agent(Settings())

    assert _model_name_of(agent) == "qwen2.5:0.5b"


def test_build_agent_converts_timeout_ms_to_seconds(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM__TIMEOUT_MS", "42000")

    agent = build_agent(Settings())

    assert _model_settings_of(agent).get("timeout") == pytest.approx(42.0)


def test_build_agent_omits_temperature_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)

    agent = build_agent(Settings())

    assert "temperature" not in _model_settings_of(agent)


def test_build_agent_applies_temperature_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXPLAIN_WORD__TEMPERATURE", "0.15")

    agent = build_agent(Settings())

    assert _model_settings_of(agent).get("temperature") == pytest.approx(0.15)


async def test_explain_word_via_agent_returns_parsed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canned = WordExplanation(
        meaning="lasting a short time",
        simplified_explanation="not for long",
        synonyms=["fleeting"],
        antonyms=["permanent"],
    )
    fake_run = AsyncMock()
    fake_run.return_value = _StubResult(output=canned)
    monkeypatch.setattr(
        "src.modules.explain_word.agent._AGENT",
        _StubAgent(run=fake_run),
    )

    result = await explain_word_via_agent("ephemeral", "The graffiti was ephemeral.")

    assert result is canned
    fake_run.assert_awaited_once()
    assert fake_run.await_args is not None
    rendered_prompt: str = fake_run.await_args.args[0]
    assert "ephemeral" in rendered_prompt
    assert "The graffiti was ephemeral." in rendered_prompt


class _StubAgent:
    """Duck-typed stand-in for :class:`pydantic_ai.Agent` — only ``run`` is used."""

    def __init__(self, run: AsyncMock) -> None:
        self.run = run


class _StubResult:
    """Duck-typed stand-in for :class:`pydantic_ai.agent.AgentRunResult`."""

    def __init__(self, output: Any) -> None:
        self.output = output
