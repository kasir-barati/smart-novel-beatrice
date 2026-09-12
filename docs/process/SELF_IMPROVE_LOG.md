# Self-improvement log

## 2026-09-11 — progress-callback-cadence fix, step 1

Removed the fake `percent` field from `statusCallbackUrl`'s `generating`/`uploading`
progress reports and collapsed `synthesize_job`'s two now-identical `generating` calls
into one. Updated `PROCESS.md` (step 7) to call out running `make schema` whenever a
Strawberry field/argument description changes — running it here also surfaced
unrelated drift in `docs/schema.graphql` (a stale `instruct` description) left over
from an earlier feature that changed a description without regenerating. No other
process gaps or test surprises this pass — the change was small and self-contained
enough that unit and integration tests passed on the first run.

## 2026-09-11 — clientContextId (caller-correlation-id), step 1

Added the `clientContextId` argument, threaded it onto the queue message, and echoed
it on the `queued` callback, mirroring the existing `instruct` pattern throughout
(resolver, `GenerateAudioJob`, unit tests, integration test). Everything passed on the
first run — unit, integration, and graphql-api-tester all confirmed the three ACs
with no surprises. One single-occurrence observation, not yet promoted to `PROCESS.md`
since it hasn't repeated: `docker compose up --build -d` took long enough to exceed
the default 120s Bash timeout and moved to background automatically — worth budgeting
for on a cold build, and worth polling for the specific service's health status
(`docker compose ps` showing `healthy`) rather than just "any output," since a
container can appear before it's actually ready to take traffic.

## 2026-09-11 — clientContextId (caller-correlation-id), step 2

Threaded `client_context_id` through `worker.py`'s `report_progress`/`report_completed`/
`report_failed`/`_post_status_update` and every call site, mirroring step 1's pattern.
Unit and integration tests passed on the first run; graphql-api-tester correctly
skipped per the step's Test notes (no GraphQL surface changed). The cold
`docker compose up --build -d` timeout observed in step 1 repeated here, so it's now
promoted to `PROCESS.md` step 4 instead of staying a single-occurrence log note.

## 2026-09-11 — clientContextId (caller-correlation-id), step 3

Added the `clientContextId` JSON body to `_fetch_presigned_upload_url`'s POST to
`genUploadUrl` (sent only when the job carries one; `httpx`'s `json=None` cleanly
reproduces today's no-body behavior, no branching needed on the request itself).
Unit and integration tests passed first run; graphql-api-tester correctly skipped
per the step's Test notes. No new process gaps — the `PROCESS.md` step 4 addendum
from step 2 already covered the only recurring friction (cold `docker compose
up --build`). Noted but left untouched: an unrelated working-tree change to
`.claude/skills/build-step/SKILL.md` (description/wording only, not made by this
run) was present before this step started and out of this step's scope, so it was
left unstaged rather than folded into the step 3 commit.

## 2026-09-12 — ordered TTS status callbacks, step 1

Collapsed `resolver.py`'s `_report_queued` and `worker.py`'s
`report_progress`/`report_completed`/`report_failed`/`_post_status_update` into one
`progress.report(...)` entry point in a new `progress.py`, with `revalidate=True` as
the one behavioral knob (worker's calls re-check the allow-list post-queue-hop, the
resolver's own call doesn't need to). Moved the exhaustive httpx-mocked body/header
assertions for all five statuses into `progress__test.py`; `resolver__test.py` and
`worker__test.py` now just assert their functions delegate to `progress.report` with
the right arguments (via a small `_record_progress_report` recorder), so the two
tiers of test don't duplicate the same httpx-transport coverage. No process gaps —
pure refactor, no GraphQL surface or prompt changed, so graphql-api-tester and
`make evals` were both correctly skipped per the step's Test notes; unit tests, ruff,
flake8, and pyright all passed first run.
