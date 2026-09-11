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
