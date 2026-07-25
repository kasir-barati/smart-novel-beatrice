"""
OTel helpers shared across integration tests.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


SpanDict = dict[str, Any]
SpansReader = Callable[[], list[SpanDict]]


def wait_for_spans(
    reader: SpansReader,
    predicate: Callable[[list[SpanDict]], bool],
    *,
    timeout_s: float = 10.0,
    poll_s: float = 0.25,
) -> list[SpanDict]:
    """
    Returns the final list of spans on success; raises ``TimeoutError`` otherwise.
    """
    deadline = time.monotonic() + timeout_s
    spans: list[SpanDict] = []

    while time.monotonic() < deadline:
        spans = reader()

        if predicate(spans):
            return spans

        time.sleep(poll_s)

    raise TimeoutError(
        f"predicate not satisfied within {timeout_s}s; saw {len(spans)} span(s): "
        f"{[s['name'] for s in spans]!r}"
    )


def find_spans(spans: list[SpanDict], *, name: str) -> list[SpanDict]:
    """
    Returns every span whose ``name`` matches exactly.
    """

    return [span for span in spans if span.get("name") == name]


def find_spans_with_attribute(
    spans: list[SpanDict],
    *,
    attribute: str,
) -> list[SpanDict]:
    """
    Returns every span that carries *attribute* (regardless of value).
    """

    return [span for span in spans if attribute in span.get("attributes", {})]
