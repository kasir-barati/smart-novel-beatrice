from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
from opentelemetry.sdk.trace import TracerProvider

from src.utils import (
    ExcludeGraphQLOperationsSpanProcessor,
    JsonFormatter,
    Llm,
    Logging,
    LoggingMode,
    LogLevel,
    Otel,
    Settings,
    observability,
    setup_observability,
)


@pytest.fixture(autouse=True)
def _reset_observability_state() -> Iterator[None]:
    observability._configured = False
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in original_handlers:
        root.addHandler(h)
    root.setLevel(original_level)
    observability._configured = False


def _make_settings(
    *,
    logging_mode: LoggingMode = LoggingMode.JSON,
    log_level: LogLevel = LogLevel.INFO,
    otel_enabled: bool = False,
) -> Settings:
    return Settings(
        logging=Logging(mode=logging_mode, level=log_level),
        otel=Otel(enabled=otel_enabled),
        llm=Llm(),
    )


def test_json_formatter_produces_valid_json() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    record.__dict__["custom_attr"] = 42

    result = json.loads(JsonFormatter().format(record))

    assert result["message"] == "hello world"
    assert result["level"] == "info"
    assert result["logger"] == "test"
    assert result["custom_attr"] == 42
    assert "timestamp" in result


def test_setup_configures_json_logging(caplog: pytest.LogCaptureFixture) -> None:
    settings = _make_settings(logging_mode=LoggingMode.JSON, log_level=LogLevel.INFO)

    setup_observability(settings, version="0.0.0")  # act

    root = logging.getLogger()
    assert root.level == logging.INFO
    assert any(isinstance(h.formatter, JsonFormatter) for h in root.handlers)


def test_setup_is_idempotent() -> None:
    settings = _make_settings()
    setup_observability(settings, version="0.0.0")
    handlers_after_first = list(logging.getLogger().handlers)

    setup_observability(settings, version="0.0.0")  # act

    handlers_after_second = list(logging.getLogger().handlers)
    assert handlers_after_first == handlers_after_second


def test_pretty_mode_uses_plain_formatter() -> None:
    settings = _make_settings(logging_mode=LoggingMode.PLAIN_TEXT)

    setup_observability(settings, version="0.0.0")  # act

    root = logging.getLogger()
    assert root.handlers, "expected a handler to be installed"
    assert not isinstance(root.handlers[0].formatter, JsonFormatter)


def test_tracing_installs_operation_filter_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[TracerProvider] = []
    monkeypatch.setattr(observability.trace, "set_tracer_provider", captured.append)
    monkeypatch.setattr(
        observability,
        "HTTPXClientInstrumentor",  # HTTPXClientInstrumentor().instrument() is a global side-effect we don't want to run in this test; the tracing branch calls it near the end.
        lambda: type("_FakeInstrumentor", (), {"instrument": lambda self: None})(),
    )
    monkeypatch.setattr(
        observability,
        "AioPikaInstrumentor",  # same global-side-effect reasoning as HTTPXClientInstrumentor above.
        lambda: type("_FakeInstrumentor", (), {"instrument": lambda self: None})(),
    )
    settings = Settings(otel=Otel(enabled=True))

    setup_observability(settings, version="0.0.0")  # act

    assert any(
        isinstance(span_processor, ExcludeGraphQLOperationsSpanProcessor)
        for span_processor in list(captured[0]._active_span_processor._span_processors)
    )
