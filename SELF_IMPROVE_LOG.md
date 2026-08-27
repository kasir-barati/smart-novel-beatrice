# Self-improvement log

## Step 1 — Provider Abstraction Layer — 2026-08-27

Built `src/modules/audio/` (`TtsProvider` protocol, `Qwen3TtsProvider`, `GeminiTtsProvider`, settings, unit tests with `httpx.MockTransport`). No GraphQL surface, so `graphql-api-tester` was correctly skipped per the step's Test note — the loop's per-step test-tier guidance held up on the first real step.

Only real hiccup: typed the injectable `transport` param as `httpx.BaseTransport` first; pyright caught the mismatch against `AsyncClient`, which wants `AsyncBaseTransport`. Not a process problem — added the correct pattern to `.github/CONTRIBUTING.md` directly (per the new PROCESS.md-vs-CONTRIBUTING.md split in `SELF_IMPROVE.md` step 3) rather than touching `PROCESS.md`.

## Step 2 — `audioVoices` Query — 2026-08-27

The AC ("Accept a URL as env variable to resolve voice names") was genuinely ambiguous against step 1's design — asked the user via AskUserQuestion instead of guessing, which confirmed reusing step 1's `TtsProvider` abstraction (a new `TTS__DEFAULT_PROVIDER` env var selects which provider backs the query). Good outcome for stopping to ask on a real fork in approach rather than picking one silently.

Two process gaps surfaced, both fixed:
1. Hit a real import cycle putting `TtsProviderName` in `provider.py` once `Settings` needed to reference it too — moved it into `src/utils/config.py` alongside the other settings enums. Added as a `.github/CONTRIBUTING.md` rule (item 8) so the next provider-selecting setting doesn't rediscover this the hard way.
2. After invoking `graphql-api-tester`, spawned a stray placeholder agent trying to "wait" for it — wasteful and unnecessary, since the completion notification arrives on its own. Added a line to `PROCESS.md` step 4 against doing that again.

`graphql-api-tester` also confirmed a live-dev-server limitation worth remembering for steps 3-6: operations that call the real Qwen3-TTS/Gemini-TTS APIs will fail against `docker compose up` with a real `401`/`403` unless a real provider API key is in `.env` — expected, not a bug, and not something to "fix" by acquiring credentials. WireMock-backed integration tests plus unit tests with a fake provider remain the actual correctness signal; the live dev-server check is only useful for schema-shape/wiring checks that don't depend on the provider call succeeding.

## Step 3 — `generateAudio` Mutation (accept/validate/publish) — 2026-08-27

The largest step so far (validation, RabbitMQ publish with quorum queue + OTel instrumentation, a best-effort callback) but the per-step scoping held up fine — no need to split it further than `REQUIREMENTS.md` already had it.

Confirmed the step 2 process fixes actually stuck: no stray "wait for the agent" spawn this time, and the graphql-api-tester dev-API-key limitation from step 2's log entry recurred exactly as predicted (voice validation needs a live provider call, same 401) — briefed the tester on it upfront in the prompt this time instead of discovering it again, and it correctly worked around it (used a made-up voice name, noted which case it hit) rather than reporting a false FAIL.

One real gotcha, added to `.github/CONTRIBUTING.md` (item 9): pydantic-settings JSON-decodes any `list`-typed `BaseSettings` field read from an env var *before* field validators run, so a custom comma-split `field_validator` is dead code — confirmed by testing (`CallbackSettings.allowed_hosts` as `list[str]]` raised `SettingsError` on `"a,b"`, and reproduced the same failure on an unrelated top-level list field to confirm it's a pydantic-settings behavior, not a nesting artifact). Fixed by typing the field `str` and exposing a computed `allowed_hosts_list` property instead. Worth remembering for `x-attempt`/`x-delivery-limit` env vars in step 6 if any of those end up list-shaped.

## Step 4 — Worker Consume & Synthesize — 2026-08-27

First step with no `### AC` subsection in `REQUIREMENTS.md` at all — just the numbered description and the Test note. Scoped it directly from the numbered steps plus the shared architecture section (which spans steps 3-6); no ambiguity worth stopping to ask about this time.

One deliberate scope call, logged in case it needs revisiting: added `src/worker.py` (a real process entrypoint) and a `make start_worker` target even though the step's Test note only asked for unit-testable functions. Justification: the step description and the shared architecture section explicitly call for "a separate worker process" — without an entrypoint that claim is unbuilt, not just untested. Steps 5-6 extend the same worker, so this seemed like the right point to add it rather than retrofitting later.

Also made a deliberate, explicitly-flagged simplification: message ack/reject uses aio_pika's default `message.process()` behavior (ack on success, reject-without-requeue on any exception) as a placeholder — proper retry/DLQ decisioning (`x-attempt`, `x-delivery-limit`) is step 6's actual job, not something to half-build now.

### Off-cycle: SSRF fix (background security review, between steps 4 and 5)

A background security review flagged that the worker trusted `statusCallbackUrl` off the queue without re-checking the host allow-list — `generateAudio` validates it once at publish time, but that guarantee doesn't survive the RabbitMQ hop into a separate process. Fixed by extracting the check into `src/modules/audio/callback_urls.py`, shared by the resolver and worker. This is exactly the kind of gap `PROCESS.md`/`SELF_IMPROVE.md` don't cover — there's no step in the loop for "a security finding arrived out of band" — and it worked fine as an ad hoc fix-and-commit cycle outside the normal step loop. Not proposing a process change for this; one occurrence isn't a pattern yet.

## Step 5 — Worker Upload & Completion — 2026-08-27

Directly benefited from the off-cycle SSRF fix above: `genUploadUrl` has the exact same trust-boundary shape as `statusCallbackUrl` (validated at publish, read back off the queue by a different process), so it got the same re-validation from the start instead of needing a second security-review round-trip to discover it.

New testing-harness insight, added to `.github/CONTRIBUTING.md`: a worker/consumer fixture used in integration tests must be function-scoped, not session-scoped like the other infra fixtures — a session-scoped worker would race any test asserting on a message directly off the queue (`queue.get()`), consuming it out from under that test. `worker_container` in `tests/conftest.py` is scoped accordingly; only step 5's end-to-end test requests it, leaving step 3's raw-queue-inspection test undisturbed.

No process or CONTRIBUTING.md gaps surfaced this round — first genuinely smooth step since the harness fixes in steps 2-3 landed.

## Step 6 — Retry & DLQ — 2026-08-27

Real ambiguity in the AC text: "If step 5 failed we MUST retry" reads literally as scoping retry/DLQ to upload-phase failures only, excluding step 4's synthesis failures. Went with the broader reading (retry/DLQ applies to any pipeline failure) since a narrower reading would leave synthesis failures silently dropped with no principled reason to treat them differently — documented the reasoning in the commit message rather than the code, since it's a "why this scope" call, not a "why this line" call.

Also weighed using RabbitMQ quorum queues' *native* `x-delivery-limit` argument (a real built-in feature, name coincidentally identical to the AC's wording) against an application-level `x-attempt` header. Chose app-level: the AC explicitly describes `x-attempt` as something we manage, and only an app-level implementation gives control over the retry *delay* (RabbitMQ's native redelivery-on-nack has no built-in per-message backoff without the delayed-exchange plugin, which isn't part of this stack).

Two mistakes caught before they shipped, both from being too trusting of a bulk find/replace: a Python-heredoc regex substitution turned a test helper into an infinitely-recursive call to itself (same name pattern matched in two places), and a separate blanket string replacement stripped an unrelated `# type: ignore` comment three lines away from where I meant to strip it. Both were caught by pyright immediately after, before any test ran — but the near-miss is worth remembering: a bulk replace across a whole file needs the same "read the actual result" scrutiny as a hand-written edit, especially when the search text is short enough to match somewhere unintended.

Genuine `aio_pika` API gotcha, added to `.github/CONTRIBUTING.md`: `Queue.get(timeout=N)` is a single poll, not "wait up to N seconds" — it raises `QueueEmpty` immediately if nothing's there yet. The DLQ integration test's first draft used it expecting it to wait out the worker's retry delay, and failed until replaced with an actual poll loop.

## Step 7 — Observability & Logging — 2026-08-27

Last step in `REQUIREMENTS.md` — all 7 are now implemented and committed individually, which was the whole point of splitting the doc into steps back at the start of this project. No new ambiguity in scope this time (a long field checklist, not prose to interpret), but one real design call: `_requeue_for_retry` now refreshes the `timestamp` header on each retry-republish, so `queue_wait_seconds` measures *this* delivery's own wait rather than cumulative time since the very first attempt — the AC just says "how long it waited in the queue before being picked up," which reads as per-delivery, not per-job-across-all-retries.

Recurring pyright friction, now a `CONTRIBUTING.md` rule (item 10): asserting on a log record's `extra={...}` fields via `caplog` fails static typing because `logging.LogRecord` doesn't declare arbitrary extras, even though they're real attributes at runtime. `record: Any = next(...)` at the pull-out point is the fix — cheaper than annotating every field access.

Recursive self-improvement: `SELF_IMPROVE.md`'s routing rule (procedural → `PROCESS.md`, code pattern → `CONTRIBUTING.md`) has now correctly classified 5 gotchas in a row across steps 3-7 without needing adjustment. Not changing it — it's doing its job.
