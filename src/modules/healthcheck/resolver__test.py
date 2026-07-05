from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.modules.healthcheck import HealthCheck, healthcheck, resolver as resolver_module
from src.utils import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_healthcheck_returns_response(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM__MODEL", "qwen2.5:0.5b")
    monkeypatch.setattr(resolver_module, "version", lambda _name: "1.2.3")

    result = healthcheck()

    assert isinstance(result, HealthCheck)
    assert result.is_running is True
    assert result.model == "qwen2.5:0.5b"
    assert result.version == "1.2.3"
