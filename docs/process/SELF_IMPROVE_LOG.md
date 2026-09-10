# Self-improvement Log

## 2026-09-10 — TTS-provider-swap step 1

Removing `QwenTtsSettings.voices_path` (per the step's AC) left `qwen_provider.py`
referencing a field that no longer existed — an `AttributeError` at runtime and a
pyright error, not just a stale test. The repo's pre-commit hook runs `make test`
(full unit suite) and blocks the commit on any failure, so the step couldn't be
committed with that file left broken pending step 2, even though the requirements
doc frames the two steps as independently committable.

Fix: made the minimal change to `qwen_provider.py`'s `get_voices` (read the new
static `voices_list` instead of calling the removed path) and updated only the
directly-broken assertions in its test file (voice listing, `model` default
literal), leaving the rest of the DashScope migration (synthesize body shape,
`instruct`→`instructions`, two-hop download) untouched for step 2.

Changed `PROCESS.md` step 7 to call this out generally: a step that removes/renames
something another file depends on must fold that file's minimal fix into the same
commit, since the test gate doesn't allow a step-spanning red window.
