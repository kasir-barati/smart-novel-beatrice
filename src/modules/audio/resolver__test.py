from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.modules.audio import resolver
from src.modules.audio.types import Voice


@pytest.fixture(autouse=True)
def _clear_voices_cache() -> Iterator[None]:
    resolver._voices_cache = None
    yield
    resolver._voices_cache = None


class _FakeProvider:
    def __init__(self, voices: list[Voice]) -> None:
        self._voices = voices
        self.get_voices_call_count = 0
        self.closed = False

    async def get_voices(self, *, language: str | None = None) -> list[Voice]:
        self.get_voices_call_count += 1
        return self._voices

    async def synthesize(self, *, text: str, voice: str):  # pragma: no cover - unused here
        raise NotImplementedError

    async def aclose(self) -> None:
        self.closed = True


async def test_resolve_audio_voices_returns_provider_voice_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakeProvider([Voice(name="a"), Voice(name="b")])
    monkeypatch.setattr(resolver, "build_provider", lambda name, settings: fake_provider)

    result = await resolver.resolve_audio_voices()

    assert result == ["a", "b"]


async def test_resolve_audio_voices_closes_the_provider_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_provider = _FakeProvider([Voice(name="a")])
    monkeypatch.setattr(resolver, "build_provider", lambda name, settings: fake_provider)

    await resolver.resolve_audio_voices()

    assert fake_provider.closed is True


async def test_resolve_audio_voices_caches_across_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_provider = _FakeProvider([Voice(name="a")])
    monkeypatch.setattr(resolver, "build_provider", lambda name, settings: fake_provider)

    first = await resolver.resolve_audio_voices()
    second = await resolver.resolve_audio_voices()

    assert first == second
    assert fake_provider.get_voices_call_count == 1
