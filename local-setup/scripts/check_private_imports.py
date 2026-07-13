#!/usr/bin/env python3
"""
Custom lint: forbid importing private names from any module.

This check tightens that: **any** ``from X import _name`` (or ``import X._name`` / ``import X as _alias``) is flagged, regardless of package layout.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ROOTS = (REPO_ROOT / "src", REPO_ROOT / "tests")


@dataclass(frozen=True, slots=True)
class Violation:
    """One offending import in one file."""

    path: Path
    line: int
    col: int
    imported_name: str
    module: str | None
    kind: Literal["from-import", "import", "import-as"]

    def format(self) -> str:
        rel = self.path.relative_to(REPO_ROOT)

        if self.kind == "from-import":
            detail = f"private name `{self.imported_name}` imported from `{self.module}`"
        elif self.kind == "import":
            detail = f"private attribute `{self.imported_name}` referenced via `import {self.module}.{self.imported_name}`"
        else:
            detail = f"private alias `{self.imported_name}` for module `{self.module}`"

        return f"{rel}:{self.line}:{self.col}: {detail}"


def _is_private(name: str) -> bool:
    """
    True if *name* is private per our convention.

    NOTE:

    - Starts with ``_``.
    - Not a dunder (``__x__``): dunders are Python protocol, not "private".
    """

    if not name.startswith("_"):
        return False
    return not (name.startswith("__") and name.endswith("__") and len(name) >= 4)


def _iter_python_files(roots: Iterable[Path]) -> Iterator[Path]:
    for root in roots:
        if not root.exists():
            continue

        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue  # Skip caches — nothing else lives under __pycache__ we care about.

            yield path


def _check_file(path: Path) -> list[Violation]:
    violations: list[Violation] = []

    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        # Let ruff/pyright complain about syntax; not this checker's job.
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""

            for alias in node.names:
                if alias.name == "*":
                    continue

                if _is_private(alias.name):
                    violations.append(
                        Violation(
                            path=path,
                            line=alias.lineno,
                            col=alias.col_offset,
                            imported_name=alias.name,
                            module=module,
                            kind="from-import",
                        ),
                    )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                # `import pkg._mod` — the last dotted segment counts.
                last_segment = alias.name.rsplit(".", 1)[-1]

                if _is_private(last_segment):
                    violations.append(
                        Violation(
                            path=path,
                            line=alias.lineno,
                            col=alias.col_offset,
                            imported_name=last_segment,
                            module=alias.name,
                            kind="import",
                        ),
                    )
                    continue

                # `import pkg.mod as _alias` — the alias itself is private.
                if alias.asname is not None and _is_private(alias.asname):
                    violations.append(
                        Violation(
                            path=path,
                            line=alias.lineno,
                            col=alias.col_offset,
                            imported_name=alias.asname,
                            module=alias.name,
                            kind="import-as",
                        ),
                    )
    return violations


def check(roots: Iterable[Path] = DEFAULT_ROOTS) -> list[Violation]:
    """
    Return every violation found under roots
    """

    all_violations: list[Violation] = []

    for path in _iter_python_files(roots):
        all_violations.extend(_check_file(path))

    return all_violations


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv:
        roots: Iterable[Path] = [Path(a).resolve() for a in argv]
    else:
        roots = DEFAULT_ROOTS

    violations = check(roots)

    if not violations:
        return 0

    for v in violations:
        print(v.format(), file=sys.stderr)

    print(f"\n{len(violations)} private-import violation(s) found.", file=sys.stderr)

    return 1


if __name__ == "__main__":
    sys.exit(main())
