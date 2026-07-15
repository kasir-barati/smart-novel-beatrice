"""
Application configuration — every knob comes from an environment variable.
"""

from __future__ import annotations

import tomllib
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggingMode(StrEnum):
    JSON = "JSON"
    PLAIN_TEXT = "PLAIN_TEXT"


class LogLevel(StrEnum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"


class Logging(BaseSettings):
    mode: LoggingMode = Field(
        default=LoggingMode.JSON,
        description="Structured JSON logs (prod) or plain-text logs (dev).",
    )
    level: LogLevel = Field(default=LogLevel.INFO)


class Llm(BaseSettings):
    """OpenAI-compatible Model backend"""

    base_url: str = Field(
        default="http://ollama:11434/v1",
        description="OpenAI-compatible endpoint (Ollama, vLLM, OpenAI, …).",
    )
    api_key: str = Field(
        default="ollama",
        description="Ollama accepts any non-empty string; real providers need a real key.",
    )
    model: str = Field(
        default="llama3.2:1b",
        description="Default model name for all endpoints unless overridden.",
    )
    timeout_ms: int = Field(
        default=30_000,
        ge=1_000,
        description="Timeout for individual LLM calls, in milliseconds.",
    )


class EndpointOverride(BaseSettings):
    """Optional per-endpoint LLM overrides. Leave unset to fall back to :class:`Llm`"""

    model: str | None = Field(default=None)
    temperature: float | None = Field(default=None)


class NormalizeTtsOverride(EndpointOverride):
    """
    Adds the safety threshold used to decide when to reject an LLM output that strayed too far from the input length.
    """

    max_length_deviation: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
    )


class Otel(BaseSettings):
    """OpenTelemetry configuration"""

    enabled: bool = Field(default=False)
    exporter_otlp_endpoint: str = Field(default="http://otel-collector:4318")
    traces_sampler: str = Field(default="parentbased_always_on")


class Settings(BaseSettings):
    """Runtime configuration surface"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="__",
        extra="ignore",
    )

    port: int = Field(default=3000, description="HTTP port to bind.")
    service_name: str = Field(
        default="beatrice",
        description="Reported to OTel and used as a general service identifier.",
    )

    @property
    def app_name(self) -> str:
        """Read ``[project].name`` from pyproject.toml at runtime."""

        pyproject = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

        return data["project"]["name"]

    logging: Logging = Field(default_factory=Logging)
    llm: Llm = Field(default_factory=Llm)
    explain_word: EndpointOverride = Field(default_factory=EndpointOverride)
    normalize_tts: NormalizeTtsOverride = Field(default_factory=NormalizeTtsOverride)
    otel: Otel = Field(default_factory=Otel)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton"""

    return Settings()
