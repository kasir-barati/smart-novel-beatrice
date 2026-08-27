from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.modules.audio.callback_urls import CallbackUrlNotAllowedError, validate_callback_url
from src.utils import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_validate_callback_url_accepts_an_allow_listed_https_host(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GENERATE_AUDIO__CALLBACK__ALLOWED_HOSTS", "client.example.com")

    result = validate_callback_url("https://client.example.com/webhook")

    assert result == "https://client.example.com/webhook"


def test_validate_callback_url_rejects_non_http_scheme(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GENERATE_AUDIO__CALLBACK__ALLOWED_HOSTS", "client.example.com")

    with pytest.raises(CallbackUrlNotAllowedError, match="absolute http"):
        validate_callback_url("ftp://client.example.com/webhook")


def test_validate_callback_url_rejects_a_host_not_on_the_allow_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GENERATE_AUDIO__CALLBACK__ALLOWED_HOSTS", "client.example.com")

    with pytest.raises(CallbackUrlNotAllowedError, match="not in the allow-list"):
        validate_callback_url("https://evil.example.com/webhook")
