"""
Run the ``explainWord`` eval suite against the currently-configured LLM.

- Invoked by ``make evals`` (once per module).
- Reads ``dataset.yaml`` in this directory, runs the agent on every case, applies structural evaluators, and writes a JSON report to ``report.json``.
- Baseline scores live in ``baseline.json``.
- Running ``make evals`` fails if any case regresses; running ``make evals_baseline`` overwrites the baseline in-place after a deliberate quality improvement.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from src.modules.explain_word.agent import explain_word_via_agent
from src.modules.explain_word.types import WordExplanation


HERE = Path(__file__).resolve().parent
DATASET_PATH = HERE / "dataset.yaml"
BASELINE_PATH = HERE / "baseline.json"
REPORT_PATH = HERE / "report.json"


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


# ---------------------------------------------------------------------------
# Dataset loading — we don't rely on pydantic-evals' YAML machinery because our dataclasses aren't Pydantic models. Manual load keeps the dataset file obvious and dependency-lean.
# ---------------------------------------------------------------------------
def _load_dataset() -> Dataset[ExplainWordInputs, WordExplanation, ExplainWordMetadata]:
    import yaml

    raw = yaml.safe_load(DATASET_PATH.read_text(encoding="utf-8"))
    cases: list[Case[ExplainWordInputs, WordExplanation, ExplainWordMetadata]] = []

    for row in raw["cases"]:
        cases.append(
            Case(
                name=row["name"],
                inputs=ExplainWordInputs(**row["inputs"]),
                metadata=ExplainWordMetadata(**row["metadata"]),
            ),
        )
    return Dataset(name="explain_word", cases=cases, evaluators=EVALUATORS)


async def _task(inputs: ExplainWordInputs) -> WordExplanation:
    return await explain_word_via_agent(word=inputs.word, context=inputs.context)


# ---------------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------------
def _extract_scores(report: Any) -> dict[str, dict[str, bool]]:
    """Reduce a pydantic-evals report to ``{case_name: {evaluator_name: bool}}``."""

    scores: dict[str, dict[str, bool]] = {}

    for case in report.cases:
        case_scores: dict[str, bool] = {}

        for evaluation in case.assertions.values():
            case_scores[evaluation.name] = bool(evaluation.value)

        scores[case.name] = case_scores

    return scores


def _load_baseline() -> dict[str, dict[str, bool]] | None:
    if not BASELINE_PATH.exists():
        return None

    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _write_baseline(scores: dict[str, dict[str, bool]]) -> None:
    BASELINE_PATH.write_text(json.dumps(scores, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_report(scores: dict[str, dict[str, bool]]) -> None:
    REPORT_PATH.write_text(json.dumps(scores, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _diff_against_baseline(
    current: dict[str, dict[str, bool]],
    baseline: dict[str, dict[str, bool]],
) -> list[str]:
    regressions: list[str] = []

    for case_name, case_scores in baseline.items():
        for eval_name, was_passing in case_scores.items():
            if not was_passing:
                continue

            now_passing = current.get(case_name, {}).get(eval_name, False)

            if not now_passing:
                regressions.append(f"{case_name}::{eval_name}")

    return regressions


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def _run_async(update_baseline: bool) -> int:
    dataset = _load_dataset()

    print(f"Running {len(dataset.cases)} case(s) against the current agent...")

    report = await dataset.evaluate(_task)
    scores = _extract_scores(report)

    print(json.dumps(scores, indent=2, sort_keys=True))

    _write_report(scores)

    if update_baseline:
        _write_baseline(scores)

        print(f"Baseline updated → {BASELINE_PATH}")

        return 0

    baseline = _load_baseline()

    if baseline is None:
        _write_baseline(scores)

        print(f"No prior baseline — wrote current scores to {BASELINE_PATH}")

        return 0

    regressions = _diff_against_baseline(scores, baseline)

    if regressions:
        print("REGRESSIONS detected vs. baseline:")

        for r in regressions:
            print(f"  - {r}")

        return 1

    print("No regressions vs. baseline.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the explainWord eval suite.")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite baseline.json with the current run's scores.",
    )
    args = parser.parse_args()

    return asyncio.run(_run_async(update_baseline=args.update_baseline))


if __name__ == "__main__":
    sys.exit(main())
