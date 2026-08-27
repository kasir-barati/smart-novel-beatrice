# Self-improvement log

## Step 1 — Provider Abstraction Layer — 2026-08-27

Built `src/modules/audio/` (`TtsProvider` protocol, `Qwen3TtsProvider`, `GeminiTtsProvider`, settings, unit tests with `httpx.MockTransport`). No GraphQL surface, so `graphql-api-tester` was correctly skipped per the step's Test note — the loop's per-step test-tier guidance held up on the first real step.

Only real hiccup: typed the injectable `transport` param as `httpx.BaseTransport` first; pyright caught the mismatch against `AsyncClient`, which wants `AsyncBaseTransport`. Not a process problem — added the correct pattern to `.github/CONTRIBUTING.md` directly (per the new PROCESS.md-vs-CONTRIBUTING.md split in `SELF_IMPROVE.md` step 3) rather than touching `PROCESS.md`.
