from __future__ import annotations

import os


def _sanitize_env_for_tests() -> None:
    """
    Force OTel off and drop stale exporter endpoints from a dev ``.env``, and backfill the
    handful of settings (RabbitMq/Llm/Otel/TTS provider credentials) that have no code default
    on purpose — every real environment must set them explicitly, but unit tests that `chdir`
    away from the repo's `.env` still need a value to construct `Settings()`.
    """

    os.environ["OTEL__ENABLED"] = "false"
    for key in list(os.environ):
        if key.startswith("OTEL__EXPORTER_"):
            os.environ.pop(key, None)
    os.environ["OTEL__EXPORTER_OTLP_ENDPOINT"] = "http://otel-collector:4318"
    os.environ.setdefault("LLM__BASE_URL", "http://ollama:11434/v1")
    os.environ.setdefault("LLM__API_KEY", "ollama")
    os.environ.setdefault("LLM__MODEL", "qwen2.5:3b")
    os.environ.setdefault("RABBITMQ__CONNECTION_STRING", "amqp://guest:guest@rabbitmq:5672/")
    os.environ.setdefault("TTS__QWEN__API_KEY", "test-key")


_sanitize_env_for_tests()
