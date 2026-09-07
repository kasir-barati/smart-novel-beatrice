# Self-Improvement Log

## 2026-09-07 — instruct feature, step 1 (Provider Layer — instruct Plumbing)

Clean pass: tests, ruff, flake8-aaa, and pyright all passed first try. No GraphQL surface
in this step so graphql-api-tester was correctly skipped per `PROCESS.md`. No process or
code-philosophy gaps surfaced — nothing to change in `PROCESS.md` or `CONTRIBUTING.md`.

## 2026-09-07 — instruct feature, step 2 (generateAudio Mutation — Accept & Validate instruct)

graphql-api-tester confirmed all applicable AC live (validation-before-publish, Qwen+instruct
happy path, no length cap, backward-compat when omitted/null). One gap: the step's `### Test`
asked for both the accept-when-Qwen and reject-when-Gemini paths at the integration tier, but
`app_container` is session-scoped and fixed to Qwen3-TTS — reconfiguring it per-test isn't
practical, so the reject path stayed unit-only (documented in the test file). Added a note to
`PROCESS.md` step 5 so future steps check this before assuming a config-dependent branch is
integration-testable against the shared fixtures.

## 2026-09-07 — instruct feature, step 3 (Worker — Forward instruct to the Provider)

Clean pass: unit tests, the extended pipeline integration test (asserting instruct reaches
the provider's wiremock-stubbed /v1/audio/speech request body via worker_container), ruff,
flake8-aaa, and pyright all passed first try. No GraphQL surface changed, so
graphql-api-tester was correctly skipped. Nothing to change in PROCESS.md or CONTRIBUTING.md.

## 2026-09-07 — instruct feature, step 4 (Local Qwen3-TTS Shim — Preset Speakers + instruct)

Manual verification (this step has no pytest tier) caught two things the written step
couldn't have anticipated: (1) Qwen3-TTS checkpoints each support exactly one generation
method — `generate_custom_voice` doesn't exist on the `-Base` checkpoint the shim was
already downloading, so `QWEN_TTS_MODEL`'s default had to move to the `-CustomVoice`
checkpoint in both `server.py` and `compose.yml`'s build arg (two places, easy to miss one).
(2) The `-CustomVoice` checkpoint's CPU inference is slow enough (30-60s for a short
sentence, on this machine under concurrent-container load) to exceed the existing 30s
`TTS__QWEN__TIMEOUT_MS`, so that had to be raised too. Neither was in the original AC —
added a CONTRIBUTING.md-style note to PROCESS.md: when a step's Test subsection says
"verify manually," budget for the possibility that manual verification surfaces
environment/dependency facts (a library's model-checkpoint capabilities, realistic
CPU timing) no amount of code review would have caught, and update the step's own AC
retroactively so the requirements doc reflects what was actually true, not just what
was planned.
