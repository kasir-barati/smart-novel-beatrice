"""Public API for src.utils"""

from __future__ import annotations

from src.utils.config import (
    EndpointOverride,
    GeminiTtsSettings,
    Llm,
    Logging,
    LoggingMode,
    LogLevel,
    NormalizeTtsOverride,
    Otel,
    QwenTtsSettings,
    Settings,
    Tts,
    TtsProviderName,
    get_settings,
)
from src.utils.evals import EvalRunner
from src.utils.exceptions import LLM_ERROR_CODE, AppError, LlmError
from src.utils.graphql_span_rename import (
    GraphqlSpanRenameExtension,
    graphql_root_span_hook,
)
from src.utils.observability import (
    JsonFormatter,
    instrument_fastapi,
    setup_observability,
)
from src.utils.prompt_loader import load_prompt
from src.utils.pydantic_validation import (
    PydanticConstraintsExtension,
    apply_pydantic_validation,
)
from src.utils.span_filter import ExcludeGraphQLOperationsSpanProcessor
from src.utils.spectaql_directive import (
    Spectaql,
    SpectaqlOption,
    spectaql_example,
    spectaql_examples,
)


__all__ = [
    "LLM_ERROR_CODE",
    "AppError",
    "EndpointOverride",
    "EvalRunner",
    "ExcludeGraphQLOperationsSpanProcessor",
    "GeminiTtsSettings",
    "GraphqlSpanRenameExtension",
    "JsonFormatter",
    "Llm",
    "LlmError",
    "LogLevel",
    "Logging",
    "LoggingMode",
    "NormalizeTtsOverride",
    "Otel",
    "PydanticConstraintsExtension",
    "QwenTtsSettings",
    "Settings",
    "Spectaql",
    "SpectaqlOption",
    "Tts",
    "TtsProviderName",
    "apply_pydantic_validation",
    "get_settings",
    "graphql_root_span_hook",
    "instrument_fastapi",
    "load_prompt",
    "setup_observability",
    "spectaql_example",
    "spectaql_examples",
]
