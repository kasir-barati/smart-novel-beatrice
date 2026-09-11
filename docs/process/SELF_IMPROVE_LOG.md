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
