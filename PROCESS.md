## Building TTS Generation Feature Process

`REQUIREMENTS.md` is split into independently-committable steps. Work ONE step per pass through this loop.

1. Check `git log` / the current code to find the next unimplemented step in `REQUIREMENTS.md`. Do not redo a step that's already merged, and do not start a later step early just because it's convenient.
2. Build only that step's scope.
3. Add tests at the tier `.github/CONTRIBUTING.md` calls for (unit for pure logic, integration for a new/changed GraphQL operation or worker path, evals for prompt changes). Each step's "Test" subsection in `REQUIREMENTS.md` says which tiers apply and whether graphql-api-tester is relevant.
4. If the step exposes or changes a GraphQL query/mutation, invoke the graphql-api-tester subagent with: the operation name(s), their file path, and the step's AC. Skip this for steps with no GraphQL surface (worker-only or logging-only steps) — invoking it with nothing new to test wastes the call.
5. Incorporate whatever graphql-api-tester or the test suite surfaces.
6. Run `make evals` if any `prompts/*.jinja2` file changed; if the regression is deliberate, commit the updated baseline per `.github/CONTRIBUTING.md`.
7. Commit the step on its own, with a message naming the `REQUIREMENTS.md` step number.
8. IMPORTANT: follow the instructions in `SELF_IMPROVE.md` to improve yourself.

You MUST complete step 8 (self-improvement) before you stop.
