"""
Run the ``explainWord`` eval suite against the currently-configured LLM.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from src.modules.explain_word.agent import explain_word_via_agent
from src.modules.explain_word.types import WordExplanation
from src.utils import EvalRunner


HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Domain types for the harness
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ExplainWordInputs:
    """One dataset row."""

    word: str
    context: str


@dataclass(frozen=True, slots=True)
class ExplainWordMetadata:
    """Per-case metadata used by the structural evaluators."""

    expected_meaning_contains: list[str]


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------
@dataclass
class MeaningMentionsExpectedKeyword(
    Evaluator[ExplainWordInputs, WordExplanation, ExplainWordMetadata],
):
    """Assert the generated meaning contains at least one expected keyword."""

    def evaluate(
        self,
        ctx: EvaluatorContext[ExplainWordInputs, WordExplanation, ExplainWordMetadata],
    ) -> bool:
        if ctx.output is None or ctx.metadata is None:
            return False

        meaning = ctx.output.meaning.lower()

        return any(keyword.lower() in meaning for keyword in ctx.metadata.expected_meaning_contains)


@dataclass
class DoesNotIncludeWordInSynonyms(
    Evaluator[ExplainWordInputs, WordExplanation, ExplainWordMetadata],
):
    """Synonyms must never include the input word itself."""

    def evaluate(
        self,
        ctx: EvaluatorContext[ExplainWordInputs, WordExplanation, ExplainWordMetadata],
    ) -> bool:
        if ctx.output is None:
            return False

        word = ctx.inputs.word.lower()

        return word not in [s.lower() for s in ctx.output.synonyms]


@dataclass
class HasNonEmptyMeaning(
    Evaluator[ExplainWordInputs, WordExplanation, ExplainWordMetadata],
):
    """Meaning and simplified explanation must both be non-empty strings."""

    def evaluate(
        self,
        ctx: EvaluatorContext[ExplainWordInputs, WordExplanation, ExplainWordMetadata],
    ) -> bool:
        if ctx.output is None:
            return False

        return bool(ctx.output.meaning.strip() and ctx.output.simplified_explanation.strip())


EVALUATORS: list[Evaluator[ExplainWordInputs, WordExplanation, ExplainWordMetadata]] = [
    MeaningMentionsExpectedKeyword(),
    DoesNotIncludeWordInSynonyms(),
    HasNonEmptyMeaning(),
]


async def _task(inputs: ExplainWordInputs) -> WordExplanation:
    return await explain_word_via_agent(word=inputs.word, context=inputs.context)


if __name__ == "__main__":
    runner: EvalRunner[ExplainWordInputs, WordExplanation, ExplainWordMetadata] = EvalRunner(
        dataset_name="explain_word",
        dataset_path=HERE / "dataset.yaml",
        baseline_path=HERE / "baseline.json",
        report_path=HERE / "report.json",
        inputs_cls=ExplainWordInputs,
        metadata_cls=ExplainWordMetadata,
        evaluators=EVALUATORS,
        task=_task,
    )

    sys.exit(runner.cli())
