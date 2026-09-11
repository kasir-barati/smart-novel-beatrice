# Requirements

## Summary

`generateAudio` returns a Beatrice-minted `jobId`, and the caller only learns it once the
mutation response arrives. Meanwhile Beatrice publishes the job to RabbitMQ and returns
immediately, so a worker can start POSTing `statusCallbackUrl` updates (`queued`,
`generating`, ...) before the caller has finished receiving the mutation response, let
alone recorded `jobId` anywhere. A caller that maintains its own `jobId -> <caller
concept>` map (e.g. smart-novel's backend mapping `jobId -> chapterId`) can only populate
that map after the mutation resolves, so an early callback has nowhere to route to and is
dropped — see `beatrice-issue-caller-correlation-id.md`. No storage backend fix closes
this window; the race is inherent to "caller only learns the correlation key after the
callback can already fire."

Add an optional, opaque `clientContextId: String` argument to `generateAudio`. Beatrice
never interprets or validates it — it stores it alongside the job and echoes it back
verbatim, as `clientContextId`, in every `statusCallbackUrl` body (`queued`, `generating`,
`uploading`, `completed`, `failed`) and in the `genUploadUrl` POST. That way the caller's
own correlation value is present on the very first callback body, with no dependency on
when the mutation response happens to arrive. `jobId`'s role is unchanged (still
Beatrice's own job identity, used for idempotency and object naming) — this only adds one
caller-supplied, caller-opaque field that Beatrice passes through unchanged, omitted from
every body when the caller didn't provide one.

## Steps

Each step below is a standalone unit of work: implement it, test it at the tier
`.github/CONTRIBUTING.md` calls for, commit it, then move to the next. Follow
`PROCESS.md` for the per-step loop.

## 1. Add `clientContextId` argument, thread it onto the queue message, echo it on `queued`

- `src/modules/audio/resolver.py`:
  - Add a new `client_context_id: Annotated[str | None, strawberry.argument(description=...)] = None`
    parameter to `generate_audio`, describing it as an opaque caller-supplied value
    Beatrice stores and echoes verbatim on every `statusCallbackUrl` body and the
    `genUploadUrl` POST, never interpreted or validated.
  - Include it in `message_body` under the key `"clientContextId"` only when not `None`
    (same pattern as `instruct`).
  - Pass it through to `_report_queued` and include it in the `queued` callback body
    (`{"status": "queued", "jobId": job_id, "clientContextId": ...}`) only when not
    `None`.
  - Update the `status_callback_url` argument's `description` example bodies to show
    `clientContextId` as an optional trailing field on `queued` (and note the other
    statuses carry it too — covered by step 2).
  - Update the `gen_upload_url` argument's `description` to note the callback now
    receives a JSON body `{"clientContextId": "<value>"}` when the caller supplied one
    (covered by step 3, but the description belongs on this argument).
- `src/modules/audio/types.py`: add `client_context_id: str | None = Field(default=None,
  alias="clientContextId")` to `GenerateAudioJob`.
- Regenerate `docs/schema.graphql` via `make schema`.

### AC

- `generateAudio` accepts an optional `clientContextId: String` argument.
- When provided, it appears verbatim as `"clientContextId"` in the RabbitMQ message body
  and in the `queued` `statusCallbackUrl` body.
- When omitted, no `clientContextId` key appears anywhere (no `null` placeholder).

### Test

- Unit (`src/modules/audio/resolver__test.py`): add
  `test_generate_audio_includes_client_context_id_in_published_body_when_given` and
  `test_generate_audio_omits_client_context_id_from_published_body_when_absent`,
  mirroring the existing `instruct` pair. Add
  `test_generate_audio_includes_client_context_id_in_queued_callback_when_given` (and an
  omitted-case counterpart) alongside
  `test_generate_audio_does_not_fail_when_queued_callback_errors`.
- Unit (`src/modules/audio/types__test.py`): assert `GenerateAudioJob` round-trips
  `clientContextId` via its alias, and defaults to `None` when absent (matching the
  existing `instruct` coverage).
- Integration (`tests/test_generate_audio_graphql.py`): add a
  `clientContextId` variable to `GENERATE_AUDIO_MUTATION` and a test asserting the
  published queue payload and the `queued` callback body both carry it when supplied;
  leave the existing tests unmodified (they don't pass it, so it must stay absent from
  their assertions).
- No `prompts/*.jinja2` changed — skip `make evals`.
- Invoke graphql-api-tester: `generateAudio` gained a new optional argument.

## 2. Echo `clientContextId` on `generating`/`uploading`/`completed`/`failed`

- `src/modules/audio/worker.py`:
  - Thread `client_context_id: str | None` through `report_progress`, `report_completed`,
    `report_failed`, and `_post_status_update`, adding it to the body only when not
    `None` (same omit-when-absent rule as step 1).
  - Update every call site (`synthesize_job`, `upload_job`, `_handle_job_failure`,
    `handle_message`'s `report_completed` call) to pass `job.client_context_id`.
- `src/modules/audio/resolver.py`: finish the `status_callback_url` description update
  started in step 1 — show `clientContextId` as an optional trailing field on every
  example body, not just `queued`.

### AC

- Every `statusCallbackUrl` POST (`queued` through step 1, plus `generating`,
  `uploading`, `completed`, `failed`) carries `clientContextId` verbatim when the job was
  published with one, and omits the key entirely when it wasn't.

### Test

- Unit (`src/modules/audio/worker__test.py`): extend
  `test_report_progress_posts_status`, `test_report_completed_posts_status_and_file_size`,
  and `test_report_failed_posts_status_error_code_and_message` with a
  `client_context_id` case each (present and absent), and update
  `test_synthesize_job_reports_progress_then_calls_the_provider` /
  `test_upload_job_fetches_presigned_url_and_puts_the_file` to assert the value is
  forwarded from the `GenerateAudioJob` fixture used in those tests.
- Integration (`tests/test_generate_audio_graphql.py`): extend
  `test_generate_audio_pipeline_uploads_the_file_and_reports_completion` (or add a
  sibling) to pass `clientContextId` and assert it's present on every status update in
  `statuses_seen`'s underlying bodies, including `completed`.
- No `prompts/*.jinja2` changed — skip `make evals`.
- Skip graphql-api-tester: no GraphQL argument/type changed in this step, only the
  out-of-band HTTP callback bodies — already covered by the integration test above.

## 3. Echo `clientContextId` on the `genUploadUrl` POST

- `src/modules/audio/worker.py`: `_fetch_presigned_upload_url` currently POSTs to
  `genUploadUrl` with no body (only the `Idempotency-Key` header). Add a JSON body,
  `{"clientContextId": "<value>"}`, sent only when `job.client_context_id` is not `None`
  (an empty body — today's behavior — when absent, not `{}`). Thread
  `client_context_id: str | None` through from `upload_job`.

### AC

- The `genUploadUrl` POST carries a JSON body `{"clientContextId": "<value>"}` when the
  job was published with one, and no body (today's behavior) when it wasn't.

### Test

- Unit (`src/modules/audio/worker__test.py`): extend
  `test_upload_job_fetches_presigned_url_and_puts_the_file` (or add a sibling) to assert
  the `genUploadUrl` request body when `client_context_id` is set, and that no body is
  sent when it's `None`.
- Integration (`tests/test_generate_audio_graphql.py`): extend the pipeline test from
  step 2 to also assert on `wiremock.requests_for("/upload")[0]["body"]`.
- No `prompts/*.jinja2` changed — skip `make evals`.
- Skip graphql-api-tester: no GraphQL argument/type changed in this step.
