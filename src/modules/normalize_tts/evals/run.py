"""
Run the ``normalizeTextForTts`` eval suite against the currently-configured LLM.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from src.modules.normalize_tts.agent import normalize_tts_via_agent
from src.modules.normalize_tts.types import NormalizedText
from src.utils import EvalRunner


HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Domain types for the harness
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class NormalizeTtsInputs:
    """One dataset row."""

    text: str


@dataclass(frozen=True, slots=True)
class NormalizeTtsMetadata:
    """Per-case structural checks."""

    must_contain: list[str]
    must_not_contain: list[str]


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------
@dataclass
class ProducesNonEmptyOutput(
    Evaluator[NormalizeTtsInputs, NormalizedText, NormalizeTtsMetadata],
):
    """The normalised output must be a non-empty, non-whitespace string."""

    def evaluate(
        self,
        ctx: EvaluatorContext[NormalizeTtsInputs, NormalizedText, NormalizeTtsMetadata],
    ) -> bool:
        if ctx.output is None:
            return False

        return bool(ctx.output.normalized_text.strip())


@dataclass
class ContainsExpectedSubstring(
    Evaluator[NormalizeTtsInputs, NormalizedText, NormalizeTtsMetadata],
):
    """Every ``must_contain`` substring must appear (case-insensitive) in the output."""

    def evaluate(
        self,
        ctx: EvaluatorContext[NormalizeTtsInputs, NormalizedText, NormalizeTtsMetadata],
    ) -> bool:
        if ctx.output is None or ctx.metadata is None:
            return False

        if not ctx.metadata.must_contain:
            return True

        haystack = ctx.output.normalized_text.lower()

        return all(needle.lower() in haystack for needle in ctx.metadata.must_contain)


@dataclass
class DoesNotContainForbiddenSubstring(
    Evaluator[NormalizeTtsInputs, NormalizedText, NormalizeTtsMetadata],
):
    """No ``must_not_contain`` substring may appear (case-sensitive) in the output."""

    def evaluate(
        self,
        ctx: EvaluatorContext[NormalizeTtsInputs, NormalizedText, NormalizeTtsMetadata],
    ) -> bool:
        if ctx.output is None or ctx.metadata is None:
            return False

        if not ctx.metadata.must_not_contain:
            return True

        haystack = ctx.output.normalized_text

        return all(needle not in haystack for needle in ctx.metadata.must_not_contain)


EVALUATORS: list[Evaluator[NormalizeTtsInputs, NormalizedText, NormalizeTtsMetadata]] = [
    ProducesNonEmptyOutput(),
    ContainsExpectedSubstring(),
    DoesNotContainForbiddenSubstring(),
]


async def _task(inputs: NormalizeTtsInputs) -> NormalizedText:
    return await normalize_tts_via_agent(text=inputs.text)


if __name__ == "__main__":
    runner: EvalRunner[NormalizeTtsInputs, NormalizedText, NormalizeTtsMetadata] = EvalRunner(
        dataset_name="normalize_tts",
        dataset_path=HERE / "dataset.yaml",
        baseline_path=HERE / "baseline.json",
        report_path=HERE / "report.json",
        inputs_cls=NormalizeTtsInputs,
        metadata_cls=NormalizeTtsMetadata,
        evaluators=EVALUATORS,
        task=_task,
    )

    sys.exit(runner.cli())
