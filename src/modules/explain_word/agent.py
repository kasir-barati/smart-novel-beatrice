"""
pydantic-ai agent that powers the explainWord mutation.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.output import NativeOutput
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from src.modules.explain_word.types import WordExplanation
from src.utils import Settings, get_settings, load_prompt


PROMPT_VERSION = "v1"
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
settings = get_settings()


def resolve_model_settings(settings: Settings) -> ModelSettings:
    """
    Build a :class:`ModelSettings` bag from config.

    Always includes ``timeout``; includes ``temperature`` only when an override
    is set (leaving the model provider free to pick its own default otherwise).
    """

    temperature = settings.explain_word.temperature
    timeout_s = settings.llm.timeout_ms / 1000
    kwargs: dict[str, float] = {"timeout": timeout_s}
    if temperature is not None:
        kwargs["temperature"] = temperature
    return ModelSettings(**kwargs)  # type: ignore[typeddict-item]


def build_agent(settings: Settings) -> Agent[None, WordExplanation]:
    """
    Build a fresh pydantic-ai :class:`Agent` from a :class:`Settings` instance.
    """

    model_name = settings.explain_word.model or settings.llm.model
    model_settings = resolve_model_settings(settings)
    provider = OpenAIProvider(
        base_url=settings.llm.base_url,
        api_key=settings.llm.api_key,
    )
    model = OpenAIChatModel(model_name, provider=provider)

    return Agent(
        model,
        output_type=NativeOutput(WordExplanation),
        model_settings=model_settings,
    )


_AGENT: Agent[None, WordExplanation] = build_agent(settings)
"""
Module-level singleton: Agent is stateless per call so it is safe to reuse across requests. Building it once avoids re-creating the underlying HTTPX client + provider on every mutation.
"""


async def explain_word_via_agent(word: str, context: str) -> WordExplanation:
    """Calls LLM and returns the explanation of the word in the given context."""
    prompt = load_prompt(_PROMPTS_DIR, PROMPT_VERSION, word=word, context=context)
    result = await _AGENT.run(prompt)

    return result.output
