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

No process or CONTRIBUTING.md gaps surfaced this round — first genuinely smooth step since the harness fixes in steps 2-3 landed.
