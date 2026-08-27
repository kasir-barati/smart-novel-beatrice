# Contributing to `beatrice`

Thanks for helping out. This document covers the project layout and the testing philosophy so you know **which kind of test to write for what**.

## How to Start on Local Machine

- [Docker](https://www.docker.com/).
- [`uv`](https://docs.astral.sh/uv/).

```shell
make init
docker compose up --build -d
```

> [!TIP]
>
> Token/s on CPU is ~5–20 tokens/s for a 3B model (llama3.2:3b); a full `WordExplanation` with a few synonyms/antonyms is easily 150–300 tokens = 10–30s at best, more if the model stalls. So when you run it on a node/machine which does NOT have have GPU and limited RAM it will take quite a long time to get the response
>
> &mdash; Read more [here](./llm-latency-primer.md).

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
   - Mock outbound calls at the tier boundary (`httpx` for provider/callback/presigned-URL HTTP, `aio-pika` for RabbitMQ) rather than spinning up real infra.
2. Integration tests:
   - **Question:** *Do the GraphQL mutations and queries actually work end-to-end against the running app?*
   - Spin up the whole stack, hit the GraphQL endpoint over HTTP, assert on the response shape.
   - Purposefully thin — one happy-path per operation, plus one scalar/validation error path where relevant.
   - Uses [Testcontainers](https://testcontainers.com/).
   - Add an integration test when introducing a new GraphQL operation or when a bug regressed the request/response contract.
   - For the async pipeline, a worker-consuming-a-queue path is also integration-tier, even with no GraphQL operation involved. Use the shared fixtures in `tests/conftest.py` rather than hand-rolled doubles:
     - `wiremock` / `wiremock_internal_url` stand in for the client-owned callback endpoints (`genUploadUrl`, `statusCallbackUrl`) — stub a response via `wiremock.stub(...)` and assert on what Beatrice actually sent via `wiremock.requests_for(...)`. Stubs and the request journal reset after every test.
     - `presigned_upload_url_factory` / `minio_verify_client` / `minio_bucket` stand in for the S3-compatible object store — a real MinIO container with a real presigned PUT URL, not a mock of the presign/upload contract. `minio_bucket` is provisioned via the `mc` CLI, matching how a real deployment provisions buckets.
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

## Design & Code Philosophy

1. Simpler is better - **do not overcomplicate**.
2. Prefer **early returns over nested conditionals**.
3. Use vitest/pytest.
   - Use [AAA (Arrange, Act, Assert) style of writing test](https://stackoverflow.com/tags/arrange-act-assert/info).
   - [`flake8-aaa`](https://pypi.org/project/flake8-aaa/) (`make lint_check` / `make lint`, config in `.flake8`) checks AAA structure via AST — it identifies the Act block semantically (a `result = ...` assignment, `with pytest.raises(...)`, or a `# act` comment) rather than counting blank lines, and is Black/ruff-format-compatible.
   - **Known gap, confirmed against 0.17.2 (latest on PyPI):** it only checks `def test_...`, not `async def test_...` — there's no `AsyncFunctionDef` handling in its visitor at all, so it silently skips async tests entirely. Since this suite runs under `asyncio_mode = auto` and most tests are async, a clean `flake8-aaa` run is not proof of AAA compliance — it's only checking whatever sync test functions exist. Review async tests for AAA by eye; the violation this misses most often is an `assert` buried inside a mock/stub closure defined in the Arrange block (asserting on the request payload from inside the `httpx.MockTransport` handler, for example) instead of pulled out into the Assert block.
4. IMPORTANT: Avoid overly defensive programming; avoid `insistence` checks; only manage exceptions when necessary.
5. Use `uv`; ALWAYS `uv run xxx` NEVER `python3 xxx`.
6. Use latest version of libraries and idiomatic approaches as of today.
7. For a class that owns an `httpx.AsyncClient`, accept an optional `transport: httpx.AsyncBaseTransport | None = None` constructor param (forwarded to the client) so tests can inject `httpx.MockTransport` without patching internals. Type it `AsyncBaseTransport`, not `BaseTransport` — pyright rejects the sync variant against `AsyncClient`.
