---
name: build-step
description: Implement, test, and commit exactly one step of the TTS generation feature from REQUIREMENTS.md, following docs/process/PROCESS.md and docs/process/SELF_IMPROVE.md. Use when the user asks to build/continue/resume the next TTS pipeline step, or names a step number.
---

Run the loop in `docs/process/PROCESS.md` for a single step of `REQUIREMENTS.md`.

1. If the user named a step number in `args`, use it. Otherwise determine the next unimplemented step by checking `git log` and the current code against `REQUIREMENTS.md` — do not assume, verify.
2. Read only that step's section (and its `### AC` / `### Test` subsections) in `REQUIREMENTS.md`. Do not read ahead into later steps.
3. Follow `docs/process/PROCESS.md` steps 2-8 exactly, including invoking graphql-api-tester when (and only when) the step's `### Test` subsection calls for it, and the mandatory `docs/process/SELF_IMPROVE.md` pass before stopping.
4. Stop after the one step is committed. Do not chain into the next step in the same run — that defeats the point of committing/testing steps individually.
