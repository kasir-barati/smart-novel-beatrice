# Ordered TTS Status Callbacks

Wherever we talk about smart-novel we are talking about a client of Beatrice!

## Problem

The `queued` status callback is sent synchronously from the `generateAudio` resolver, right after publishing the job to RabbitMQ, over its own HTTP round-trip back to smart-novel. The `generating` callback is sent independently by the worker, the instant it dequeues that same job. Nothing coordinates these two calls, and with an empty local queue the worker can dequeue and report `generating` before the resolver's own `queued` callback completes. smart-novel has no way to tell the two apart on arrival, so whichever lands last wins — if that's `queued`, the UI gets stuck showing "Queued..." for a long time even though synthesis has already started.

## Decisions (don't relitigate these mid-implementation)

- No shared/distributed counter (Redis, DB row) to arbitrate ordering. No restructuring the pipeline into queue-per-stage. No GraphQL enum for `status` — it stays a plain string.
- Instead: every status callback carries a numeric `progress` field, source of truth owned entirely by Beatrice. smart-novel only ever compares two integers — never needs to know what stage names exist or what order they're in. Terminal statuses (`completed`, `failed`) carry no `progress` at all; they always apply immediately and end the callback stream for that job, on smart-novel's side (separate follow-up in smart-novel's own `REQUIREMENTS.md`, not this repo).
- `progress` ranking, owned by Beatrice, is not part of any public contract beyond "a bigger number is later": `queued: 1`, `generating: 2`, `uploading: 3`. Beatrice can renumber, insert, or rename stages later without smart-novel changing anything.

## Step 1: Extract a single progress-reporting module (pure refactor, no behavior change)

`_report_queued` (`src/modules/audio/resolver.py`) and `report_progress`/`report_completed`/`report_failed`/`_post_status_update` (`src/modules/audio/worker.py`) currently duplicate callback-URL validation, header assembly, and `httpx` error handling across two files. Collapse them into one new module, `src/modules/audio/progress.py`, exposing a single async entry point (e.g. `report(status_callback_url, status, *, job_id, client_context_id, authorization, **extra)`) that both `resolver.py` and `worker.py` call. `extra` covers the status-specific fields each call already sends today (`fileSizeBytes` on `completed`, `error`/`failedAt` on `failed`).

No behavior change in this step — same callback bodies as today, just one owner of the HTTP call instead of two. Keep the callback-URL re-validation `worker.py`'s `_post_status_update` already does (the resolver's own call doesn't need it — that URL was just validated by `validate_callback_url` earlier in the same request, nothing crossed a queue hop).

### AC

- `resolver.py` and `worker.py` no longer construct their own `httpx.AsyncClient` for status callbacks; both call `progress.report(...)`.
- Callback body shape, timeout, and best-effort error handling (log + swallow `httpx.HTTPError`) are unchanged from today.
- `progress.py` colocated with an equivalent httpx-mocked unit test suite (`progress__test.py`) per the `httpx-async-transport` skill.

### Test

- Unit: `progress.report` for each of the five statuses, mocked transport, asserting body/headers exactly match what `resolver.py`/`worker.py` send today.
- Existing `resolver.py`/`worker.py` unit tests updated to assert they call `progress.report` rather than asserting on `httpx` directly.
- No GraphQL surface change — skip graphql-api-tester for this step.

## Step 2: Add the `progress` field

Add a status→rank table to `progress.py` (`queued: 1, generating: 2, uploading: 3`; `completed`/`failed` map to nothing). `progress.report` looks up the rank for the given status and includes it in the callback body as `"progress": <int>` when one exists, omitting the key entirely for `completed`/`failed`.

Update the `status_callback_url` argument's docstring on `generate_audio` (`resolver.py`) to document the new field: present with an integer value on `queued`/`generating`/`uploading`, absent on `completed`/`failed`, and that consumers should treat it purely as "higher means later for this job" — no meaning attached to specific values, no guarantee they stay stable across a Beatrice release.

### AC

- Every `queued`/`generating`/`uploading` callback body includes `"progress"` with the values above; `completed`/`failed` bodies have no `progress` key.
- `generate_audio`'s docstring reflects the new field.

### Test

- Unit: extend Step 1's `progress__test.py` — one case per status asserting `progress` is present/absent/correct.
- Run `make schema` (the docstring changed) and commit the regenerated `docs/schema.graphql`.
- No GraphQL surface (arguments/types) changed beyond a description — skip graphql-api-tester.
