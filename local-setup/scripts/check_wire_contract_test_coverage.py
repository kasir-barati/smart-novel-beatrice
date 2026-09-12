#!/usr/bin/env python3
"""
Custom lint: a diff that changes a *wire-shape-relevant line* in a wire-contract
file (a GraphQL resolver, the audio worker, `progress.py`, Strawberry `types.py`,
or `schema.py`) must also touch at least one file under `tests/` — the tier that
actually asserts response/callback/queue body shape end-to-end.

"Wire-shape-relevant" is a line-level heuristic (see `_WIRE_SHAPE_MARKERS`), not a
full contract diff: it flags an added/removed line that touches a Strawberry
field/argument/type/mutation declaration, a `description=`, an outbound
json=/body=/POST/PUT construct, or a class/field definition. This is deliberately
narrower than "the file changed at all" — a renamed internal variable, an added
log line, or a comment tweak in the same file won't trip it. It's still a
heuristic, not a structural diff: a body assembled in an unusual way (e.g. via
`**kwargs` merge) could in theory slip through unflagged. When in doubt, prefer
touching a `tests/` file over trusting the heuristic — or explicitly skip this
check (`SKIP=wire-contract-coverage git commit ...` locally; pass the diff base
as argv in CI) for a change you've confirmed is genuinely wire-shape-neutral.
See REQUIREMENTS.md "Ordered TTS Status Callbacks" step 2's self-improve log
entry for the incident this check exists to catch.
"""

from __future__ import annotations

import re
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

_NULL_SHA = "0" * 40
_SHA_RE = re.compile(r"^[0-9a-fA-F]{4,40}$")

# Deliberately line-level, not file-level: matches a line that plausibly defines
# or constructs part of the wire contract, not just any line in a contract file.
_WIRE_SHAPE_MARKERS = re.compile(
    r"strawberry\.(field|argument|type|mutation|input|enum)\s*\("
    r"|\bdescription\s*="
    r"|\bjson\s*="
    r"|\bbody\s*\["
    r"|\bbody\s*="
    r"|\.post\("
    r"|\.put\("
    r"|^\s*class\s+\w+"
    r"|^\s*\w+\s*:\s*[\w\[\]\"'.| ]+(=.*)?$"  # `name: Type` / `name: Type = default` field decl
)


def _matches_contract(relative_path: str) -> bool:
    path = Path(relative_path)
    return any(path.match(pattern) for pattern in CONTRACT_GLOBS)


def _run_git(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        print(
            f"wire-contract-coverage: `{' '.join(command)}` failed ({exc}); skipping.",
            file=sys.stderr,
        )
        return None
    return result.stdout


def _changed_files(base_ref: str | None) -> list[str]:
    if base_ref is None:
        command = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    elif base_ref == _NULL_SHA:
        # `github.event.before` on a branch's first push — no prior commit to diff
        # against, so there's nothing this check can meaningfully compare.
        return []
    else:
        command = ["git", "diff", f"{base_ref}...HEAD", "--name-only", "--diff-filter=ACMR"]

    output = _run_git(command)
    return [line for line in output.splitlines() if line] if output is not None else []


def _changed_lines(path: str, base_ref: str | None) -> list[str]:
    """Added/removed line content (no +/- prefix) for one file's diff, unified with 0 context."""

    if base_ref is None:
        command = ["git", "diff", "--cached", "-U0", "--", path]
    else:
        command = ["git", "diff", f"{base_ref}...HEAD", "-U0", "--", path]

    output = _run_git(command)
    if output is None:
        return []

    lines: list[str] = []
    for line in output.splitlines():
        if line.startswith(("+++", "---", "@@", "diff --git", "index ")):
            continue
        if line.startswith(("+", "-")):
            lines.append(line[1:])
    return lines


def _is_wire_shape_change(path: str, base_ref: str | None) -> bool:
    return any(_WIRE_SHAPE_MARKERS.search(line) for line in _changed_lines(path, base_ref))


def check(base_ref: str | None) -> list[str]:
    """Return the contract files with a wire-shape-relevant change and no tests/ change."""

    # `base_ref` feeds straight into a `git diff <base_ref>...HEAD` revision spec — an
    # unvalidated value starting with `-` would be parsed as a git option, not a
    # revision (argument injection). The only legitimate values are commit SHAs (from
    # a CLI arg or `github.event.before`), so a strict hex-only pattern both rejects
    # that and rejects anything else without needing to enumerate unsafe characters.
    if base_ref is not None and base_ref != _NULL_SHA and not _SHA_RE.match(base_ref):
        print(
            f"wire-contract-coverage: base ref {base_ref!r} doesn't look like a commit "
            "SHA; skipping rather than passing it to git.",
            file=sys.stderr,
        )
        return []

    changed = _changed_files(base_ref)
    contract_candidates = [path for path in changed if _matches_contract(path)]

    if not contract_candidates:
        return []
    if any(path.startswith("tests/") for path in changed):
        return []

    return [path for path in contract_candidates if _is_wire_shape_change(path, base_ref)]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    base_ref = argv[0] if argv else None

    contract_hits = check(base_ref)

    if not contract_hits:
        return 0

    print(
        "Wire-shape-relevant change(s) with no tests/ file in the same diff:",
        file=sys.stderr,
    )
    for path in contract_hits:
        print(f"  {path}", file=sys.stderr)
    print(
        "\nIf a GraphQL response, status/upload callback, or queue message body "
        "changed shape, update the matching tests/test_*_graphql.py assertions "
        "(see .github/CONTRIBUTING.md's Testing Philosophy, tier 2). If this "
        "heuristic is wrong for this change, skip it explicitly: "
        "`SKIP=wire-contract-coverage git commit ...` locally, or pass the diff "
        "base explicitly in CI — don't silently ignore it.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
