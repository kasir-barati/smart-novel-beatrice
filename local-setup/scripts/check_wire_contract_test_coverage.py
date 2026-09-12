#!/usr/bin/env python3
"""
Custom lint: a diff that touches a wire-contract file (a GraphQL resolver, the
audio worker, `progress.py`, Strawberry `types.py`, or `schema.py`) must also
touch at least one file under `tests/` — the tier that actually asserts
response/callback/queue body shape end-to-end.

This deliberately doesn't try to tell a body-shape change apart from a pure
refactor (an AST diff can't see "the wire contract didn't change", only that
the file did) — it's cheaper to touch a `tests/` file, or explicitly skip this
check (`SKIP=wire-contract-coverage git commit ...` locally; pass the diff base
as an argv in CI), than to silently ship an untested contract change. See
REQUIREMENTS.md "Ordered TTS Status Callbacks" step 2's self-improve log entry
for the incident this check exists to catch.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

CONTRACT_GLOBS = (
    "src/schema.py",
    "src/modules/*/resolver.py",
    "src/modules/*/worker.py",
    "src/modules/*/progress.py",
    "src/modules/*/types.py",
)


def _matches_contract(relative_path: str) -> bool:
    path = Path(relative_path)
    return any(path.match(pattern) for pattern in CONTRACT_GLOBS)


_NULL_SHA = "0" * 40


def _changed_files(base_ref: str | None) -> list[str]:
    if base_ref is None:
        command = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    elif base_ref == _NULL_SHA:
        # `github.event.before` on a branch's first push — no prior commit to diff
        # against, so there's nothing this check can meaningfully compare.
        return []
    else:
        command = ["git", "diff", f"{base_ref}...HEAD", "--name-only", "--diff-filter=ACMR"]

    try:
        result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        print(
            f"wire-contract-coverage: couldn't diff against {base_ref!r} ({exc}); skipping.",
            file=sys.stderr,
        )
        return []

    return [line for line in result.stdout.splitlines() if line]


def check(base_ref: str | None) -> list[str]:
    """Return the contract files changed without a matching tests/ change; empty if OK."""

    changed = _changed_files(base_ref)
    contract_hits = [path for path in changed if _matches_contract(path)]

    if not contract_hits:
        return []
    if any(path.startswith("tests/") for path in changed):
        return []

    return contract_hits


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    base_ref = argv[0] if argv else None

    contract_hits = check(base_ref)

    if not contract_hits:
        return 0

    print(
        "Wire-contract file(s) changed with no tests/ file in the same diff:",
        file=sys.stderr,
    )
    for path in contract_hits:
        print(f"  {path}", file=sys.stderr)
    print(
        "\nIf a GraphQL response, status/upload callback, or queue message body "
        "changed shape, update the matching tests/test_*_graphql.py assertions "
        "(see .github/CONTRIBUTING.md's Testing Philosophy, tier 2). If this is "
        "genuinely a no-op refactor, skip this check explicitly: "
        "`SKIP=wire-contract-coverage git commit ...` locally, or pass the diff "
        "base explicitly in CI — don't silently ignore it.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
