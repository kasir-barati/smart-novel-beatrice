# Contributing to `beatrice`

Thanks for helping out. This document covers the project layout and the testing philosophy so you know **which kind of test to write for what**.

## How to Start on Local Machine

- [Docker](https://www.docker.com/).
- [`uv`](https://docs.astral.sh/uv/).

```shell
make init
docker compose up --build -d
```

## Project structure

```
smart-novel-beatrice/
├── src/
│   ├── main.py                       # FastAPI entrypoint, OTel bootstrap
│   ├── schema.py                     # Strawberry Query/Mutation wiring (only place resolvers are stitched together)
│   ├── modules/                      # One directory per feature — self-contained
│   │   ├── m1/
│   │   │   ├── resolver.py
│   │   │   ├── agent.py              # pydantic-ai agent
│   │   │   ├── types.py              # Strawberry + pydantic types
│   │   │   ├── prompts/v1.jinja2     # LLM prompt templates
│   │   │   ├── *__test.py            # Unit tests for each source file
│   │   │   └── evals/
│   │   │       ├── run.py            # Entrypoint invoked by `make evals`
│   │   │       ├── dataset.yaml      # Eval cases + expected metadata
│   │   │       ├── baseline.json     # Committed pass/fail matrix — the source of truth
│   │   │       └── report.json       # Last eval run output (regenerated each run)
│   └── utils/                        # Cross-cutting helpers (config, evals harness, OTel)
├── tests/                            # Integration tests only (Testcontainers-driven)
│   ├── conftest.py                   # Session fixtures
│   └── test_*_graphql.py             # One file per GraphQL operation
├── local-setup/                      # Development-only infra support (container setup, scripts, telemetry config)
├── compose.yml
├── Dockerfile
├── Makefile
└── pyproject.toml
```

- **Unit tests** are colocated with the source they cover, using the `*__test.py` suffix.

## Testing Philosophy

Three tiers. Each answers a different question. Put each new test in the tier that matches what you actually want to verify.

1. Unit tests:
   - **Question:** *Does this piece of Python behave correctly in isolation?*
   - Fast, hermetic, no Docker, no network.
   - Test whatever is easy and worthwhile to unit test: pure functions, type validation, resolver logic with the agent mocked out, error mapping, prompt-template rendering, etc.
   - If a test needs Docker or a live LLM to make sense, it is **not** a unit test — move it to integration or evals.
   - Add unit tests generously. They are cheap.
2. Integration tests:
   - **Question:** *Do the GraphQL mutations and queries actually work end-to-end against the running app?*
   - Spin up the whole stack, hit the GraphQL endpoint over HTTP, assert on the response shape.
   - Purposefully thin — one happy-path per operation, plus one scalar/validation error path where relevant.
   - Uses [Testcontainers](https://testcontainers.com/).
   - Add an integration test when introducing a new GraphQL operation or when a bug regressed the request/response contract.
3. Evals:
   - **Question:** *Are the prompts producing outputs that satisfy our rules? Is the model still doing what we expect?*
   - Use [`pydantic-evals`](https://ai.pydantic.dev/evals/) to run each module's dataset against the live LLM and score each row with a set of structural evaluators.
   - Catch:
     - Prompt edits that unintentionally degrade output quality.
     - Model changes (bumping `qwen2.5:3b` → something else) that shift behaviour.
     - Rule violations that unit tests can't express because they depend on natural-language output.

### When `make evals` Fail

**Genuine regression** (unintended): fix the prompt / code and re-run until the baseline passes again.

**Deliberate quality change** (you improved the prompt on purpose, or intentionally changed the model / temperature / rules): review the new `report.json` values, then commit the new baseline with: `make evals_baseline`

**Commit the updated baselines in the same PR as the change that caused them**, with a short justification in the commit message.
