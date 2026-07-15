"""
Shared eval runner used by every module's ``evals/run.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator


type Task[InputsT, OutputT] = Callable[[InputsT], Awaitable[OutputT]]
type Scores = dict[str, dict[str, bool]]


def extract_scores(report: Any) -> Scores:
    """
    Reduce a pydantic-evals report to ``{case_name: {evaluator_name: bool}}``.
    """

    scores: Scores = {}
    for case in report.cases:
        case_scores: dict[str, bool] = {}
        for evaluation in case.assertions.values():
            case_scores[evaluation.name] = bool(evaluation.value)
        scores[case.name] = case_scores
    return scores


def find_broken_cases(expected_case_names: Sequence[str], scores: Scores) -> list[str]:
    """
    Return the names of cases that produced zero assertions.

    A case with an empty assertions dict means the task callable raised an exception (pydantic-evals swallows per-case exceptions and continues). Treating this as a "no regression" is dangerous — it silently hides LLM outages, timeouts, and schema-validation failures, and if the baseline is then updated it becomes a permanent blind spot.
    """

    broken: list[str] = []
    for name in expected_case_names:
        case_scores = scores.get(name)
        if not case_scores:
            broken.append(name)
    return broken


def diff_against_baseline(current: Scores, baseline: Scores) -> list[str]:
    """
    Return every ``case::evaluator`` that WAS passing in *baseline* but now fails.
    """

    regressions: list[str] = []
    for case_name, case_scores in baseline.items():
        for eval_name, was_passing in case_scores.items():
            if not was_passing:
                continue
            now_passing = current.get(case_name, {}).get(eval_name, False)
            if not now_passing:
                regressions.append(f"{case_name}::{eval_name}")
    return regressions


class EvalRunner[InputsT, OutputT, MetadataT]:
    """
    Reusable driver for a module's ``evals/run.py``.

    Owns the boilerplate that should've been duplicated across every module:
    - Reading ``dataset.yaml``, materialising it into a :class:`~pydantic_evals.Dataset`.
    - Running the task, extracting boolean scores, comparing to a committed baseline, and writing a report.
    """

    def __init__(
        self,
        *,
        dataset_name: str,
        dataset_path: Path,
        baseline_path: Path,
        report_path: Path,
        inputs_cls: type[InputsT],
        metadata_cls: type[MetadataT],
        evaluators: Sequence[Evaluator[InputsT, OutputT, MetadataT]],
        task: Task[InputsT, OutputT],
    ) -> None:
        self._dataset_name = dataset_name
        self._dataset_path = dataset_path
        self._baseline_path = baseline_path
        self._report_path = report_path
        self._inputs_cls = inputs_cls
        self._metadata_cls = metadata_cls
        self._evaluators = list(evaluators)
        self._task = task

    # -- Dataset -----------------------------------------------------------
    def load_dataset(self) -> Dataset[InputsT, OutputT, MetadataT]:
        """
        Read ``dataset.yaml`` and materialise a pydantic-evals ``Dataset``.

        The YAML shape is::

            cases:
              - name: <str>
                inputs: {<inputs_cls fields>}
                metadata: {<metadata_cls fields>}
        """

        import yaml

        raw = yaml.safe_load(self._dataset_path.read_text(encoding="utf-8"))
        cases: list[Case[InputsT, OutputT, MetadataT]] = []
        for row in raw["cases"]:
            cases.append(
                Case(
                    name=row["name"],
                    inputs=self._inputs_cls(**row["inputs"]),
                    metadata=self._metadata_cls(**row["metadata"]),
                ),
            )
        return Dataset(name=self._dataset_name, cases=cases, evaluators=self._evaluators)

    # -- Baseline I/O ------------------------------------------------------
    def load_baseline(self) -> Scores | None:
        if not self._baseline_path.exists():
            return None
        return json.loads(self._baseline_path.read_text(encoding="utf-8"))

    def write_baseline(self, scores: Scores) -> None:
        self._baseline_path.write_text(
            json.dumps(scores, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def write_report(self, scores: Scores) -> None:
        self._report_path.write_text(
            json.dumps(scores, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # -- Execution ---------------------------------------------------------
    async def run(self) -> int:
        """
        Execute the suite, diff against baseline, write the report.
        """

        dataset = self.load_dataset()
        expected_case_names = [case.name for case in dataset.cases if case.name is not None]
        print(f"Running {len(dataset.cases)} case(s) against the current agent...")
        report = await dataset.evaluate(self._task)
        scores = extract_scores(report)

        print(json.dumps(scores, indent=2, sort_keys=True))
        self.write_report(scores)

        broken = find_broken_cases(expected_case_names, scores)
        if broken:
            print("BROKEN cases (task raised — zero assertions produced):")
            for name in broken:
                print(f"  - {name}")
            print(
                "This usually means the LLM call timed out, returned invalid JSON, "
                "or the Ollama endpoint is unreachable. Refusing to compare against "
                "baseline until every case runs to completion.",
            )
            return 1

        baseline = self.load_baseline()
        if baseline is None:
            self.write_baseline(scores)
            print(f"No prior baseline — wrote current scores to {self._baseline_path}")
            return 0

        regressions = diff_against_baseline(scores, baseline)
        if regressions:
            print("REGRESSIONS detected vs. baseline:")
            for r in regressions:
                print(f"  - {r}")
            return 1

        print("No regressions vs. baseline.")
        return 0

    async def update_baseline(self) -> int:
        """
        Execute the suite and overwrite the baseline with the current scores.
        """

        dataset = self.load_dataset()
        expected_case_names = [case.name for case in dataset.cases if case.name is not None]
        print(f"Running {len(dataset.cases)} case(s) against the current agent...")
        report = await dataset.evaluate(self._task)
        scores = extract_scores(report)

        print(json.dumps(scores, indent=2, sort_keys=True))
        self.write_report(scores)

        broken = find_broken_cases(expected_case_names, scores)
        if broken:
            print("BROKEN cases (task raised — zero assertions produced):")
            for name in broken:
                print(f"  - {name}")
            print(
                "Refusing to overwrite baseline with partial results. Fix the "
                "underlying LLM/task failure first, then re-run --update-baseline.",
            )
            return 1

        self.write_baseline(scores)
        print(f"Baseline updated → {self._baseline_path}")
        return 0

    # -- CLI ---------------------------------------------------------------
    def cli(self, argv: Sequence[str] | None = None) -> int:
        """
        Parse ``argv`` and dispatch to :meth:`run` or :meth:`update_baseline`.
        """

        parser = argparse.ArgumentParser(
            description=f"Run the {self._dataset_name!r} eval suite.",
        )
        parser.add_argument(
            "--update-baseline",
            action="store_true",
            help="Overwrite baseline.json with the current run's scores.",
        )
        args = parser.parse_args(argv)

        if args.update_baseline:
            return asyncio.run(self.update_baseline())
        return asyncio.run(self.run())
