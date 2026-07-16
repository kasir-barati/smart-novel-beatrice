"""Public API for src.utils"""

from __future__ import annotations

from src.utils.config import (
    EndpointOverride,
    Llm,
    Logging,
    LoggingMode,
    LogLevel,
    NormalizeTtsOverride,
    Otel,
    Settings,
    get_settings,
)
from src.utils.evals import EvalRunner
from src.utils.exceptions import LLM_ERROR_CODE, AppError, LlmError
from src.utils.graphql_scalars import SCALAR_MAP, NonEmptyTrimmedString
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
from src.utils.span_filter import ExcludeGraphQLOperationsSpanProcessor
from src.utils.spectaql_directive import (
    Spectaql,
    SpectaqlOption,
    spectaql_example,
    spectaql_examples,
)


__all__ = [
    "LLM_ERROR_CODE",
    "SCALAR_MAP",
    "AppError",
    "EndpointOverride",
    "EvalRunner",
    "ExcludeGraphQLOperationsSpanProcessor",
    "GraphqlSpanRenameExtension",
    "JsonFormatter",
    "Llm",
    "LlmError",
    "LogLevel",
    "Logging",
    "LoggingMode",
    "NonEmptyTrimmedString",
    "NormalizeTtsOverride",
    "Otel",
    "Settings",
    "Spectaql",
    "SpectaqlOption",
    "get_settings",
    "graphql_root_span_hook",
    "instrument_fastapi",
    "load_prompt",
    "setup_observability",
    "spectaql_example",
    "spectaql_examples",
]
