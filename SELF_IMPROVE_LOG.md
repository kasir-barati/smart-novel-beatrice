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
