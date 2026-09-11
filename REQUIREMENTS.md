# Requirements

## Summary

`generateAudio`'s `statusCallbackUrl` progress reports (`generating`/`uploading`) carry a
`percent` field that was never a real measurement — `GENERATING_STARTED_PERCENT` (0),
`GENERATING_CALL_PERCENT` (12), and `UPLOADING_STARTED_PERCENT` (0) are fixed markers,
not incremental progress (see `beatrice-issue-progress-callback-cadence.md`, and the
removed comment on `GENERATING_CALL_PERCENT` explaining the provider's HTTP shim exposes
no real progress signal). Remove `percent` entirely rather than keep implying a
granularity Beatrice doesn't deliver.

`synthesize_job` currently sends two `generating` reports (worker.py:144-150 right when
the job starts, worker.py:154-160 right after `build_provider()` returns, immediately
before calling `provider.synthesize(...)`) that only ever differed by `percent`.
`build_provider()` is a cheap synchronous constructor with no I/O, so nothing meaningful
happens between the two calls — once `percent` is gone they'd be byte-identical bodies
sent back-to-back. Collapse them into a single `generating` report, fired right before
`provider.synthesize(...)` is called.

The `uploading` report (worker.py:209-215, in `upload_job`) is unaffected in count —
still exactly one call — just loses `percent`.

Update `generateAudio`'s `statusCallbackUrl` argument description
(`src/modules/audio/resolver.py`) to match: drop `percent` from the example bodies, and
state plainly that each of `queued`/`generating`/`uploading`/terminal fires exactly once
per job (no repeated progress reporting) — that was already true today; this just makes
the doc match the field removal instead of leaving a stale reference to `percent`.

## Steps

Each step below is a standalone unit of work: implement it, test it at the tier
`.github/CONTRIBUTING.md` calls for, commit it, then move to the next. Follow
`PROCESS.md` for the per-step loop.

## 1. Remove `percent`, collapse the duplicate `generating` call, update docs

- `src/modules/audio/worker.py`:
  - Drop `percent` from `report_progress`'s signature and from the POST body it builds.
  - Delete `GENERATING_STARTED_PERCENT`, `GENERATING_CALL_PERCENT`,
    `UPLOADING_STARTED_PERCENT` and their docstring/comment.
  - `synthesize_job`: remove the first `report_progress` call (before `build_provider`);
    keep only the one immediately before `provider.synthesize(...)`, now without
    `percent`.
  - `upload_job`: keep its single `report_progress` call, drop `percent`.
- `src/modules/audio/resolver.py`: update the `status_callback_url` argument's
  `description` — remove `percent` from the example bodies (
  `{"status": "generating" | "uploading", "jobId": "<jobId>"}`), and state that each
  status fires exactly once per job.
- Regenerate `docs/schema.graphql` via `make schema` (source of truth per the Makefile
  comment). Do not touch the archived `docs/v3.x.x/` snapshots or `docs/latest/` —
  those are release artifacts, not edited by hand.

### AC

- No production code references `percent` in the `statusCallbackUrl` payloads anymore.
- `synthesize_job` sends exactly one `generating` report per job; `upload_job` still
  sends exactly one `uploading` report per job.
- `docs/schema.graphql`'s `statusCallbackUrl` description has no `percent` and matches
  the new example bodies exactly.

### Test

- Unit (`src/modules/audio/worker__test.py`): update
  `test_report_progress_posts_status_and_percent` (rename, drop `percent` from the
  call/assertion), the two allow-list/failure tests that pass `percent=0`, and
  `test_synthesize_job_reports_progress_then_calls_the_provider` (assert exactly one
  `generating` call, no `percent` key) and `test_upload_job_fetches_presigned_url_and_puts_the_file`
  (assert `[{"status": "uploading"}]`, no `percent`).
- Integration (`tests/test_generate_audio_graphql.py`): the existing
  `statuses_seen == ["queued", "generating", "generating", "uploading", "completed"]`
  assertion becomes `["queued", "generating", "uploading", "completed"]` (one fewer
  `generating`), and drop any `percent` assumption from that test's status bodies.
- No `prompts/*.jinja2` changed — skip `make evals`.
- Skip graphql-api-tester: `generateAudio`'s GraphQL argument/return types are unchanged
  (only a `String` description and the out-of-band HTTP callback body changed); the
  integration test above already covers the callback contract via wiremock.
