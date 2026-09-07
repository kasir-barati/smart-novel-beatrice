## Building TTS Generation Feature Process

`REQUIREMENTS.md` is split into independently-committable steps. Work ONE step per pass through this loop.

1. Check `git log` / the current code to find the next unimplemented step in `REQUIREMENTS.md`. Do not redo a step that's already merged, and do not start a later step early just because it's convenient.
2. Build only that step's scope.
3. Add tests at the tier `.github/CONTRIBUTING.md` calls for (unit for pure logic, integration for a new/changed GraphQL operation or worker path, evals for prompt changes). Each step's "Test" subsection in `REQUIREMENTS.md` says which tiers apply and whether graphql-api-tester is relevant.
4. If the step exposes or changes a GraphQL query/mutation, invoke the graphql-api-tester subagent with: the operation name(s), their file path, and the step's AC. Skip this for steps with no GraphQL surface (worker-only or logging-only steps) — invoking it with nothing new to test wastes the call. Needs a running dev server (`docker compose up --build -d`, tear down after) unless one is already up. After launching it, don't spawn another agent just to "wait" — the completion notification arrives on its own; stop and let the turn end.
5. Incorporate whatever graphql-api-tester or the test suite surfaces.
   - If a step's `### Test` subsection asks for an integration test of a behavior that depends on server config (e.g. which provider is active), check first whether the shared, session-scoped fixtures (`app_container` et al. in `tests/conftest.py`) are fixed to one configuration — they are not meant to be reconfigured per-test. When they are, cover that config-dependent branch at the unit tier instead and say so in the test file, rather than spinning up a second container (surfaced by the `instruct` feature's step 2 — the reject-when-Gemini path couldn't run against the Qwen-configured `app_container`).
6. Run `make evals` if any `prompts/*.jinja2` file changed; if the regression is deliberate, commit the updated baseline per `.github/CONTRIBUTING.md`.
   - When a step's `### Test` says to verify manually (no pytest tier — e.g. dev-only infra), budget for that verification surfacing environment/dependency facts no code review would catch (a library's model/checkpoint capabilities, realistic CPU timing under load) — actually run it rather than treating the AC as sufficient on paper. When it does surface something, fix it and update `REQUIREMENTS.md`'s AC for that step to match reality (surfaced by the `instruct` feature's step 4 — the shim's model checkpoint didn't support the target method, and the default timeout was too low for real CPU inference).
7. Commit the step on its own, with a message naming the `REQUIREMENTS.md` step number.
8. IMPORTANT: follow the instructions in `SELF_IMPROVE.md` to improve yourself.

You MUST complete step 8 (self-improvement) before you stop.
