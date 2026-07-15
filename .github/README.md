# smart-novel-beatrice

Python service exposing a **GraphQL API** for LLM-powered features used by [smart-novel](https://github.com/kasir-barati/smart-novel).

The service is **model-provider-agnostic**: it talks to any OpenAI-compatible HTTP endpoint (Ollama, vLLM, OpenAI, Together, Groq, …) via [`pydantic-ai`](https://ai.pydantic.dev). Prompts, schemas, agents, and evals live inside this repo — model choice is a config change.

## API documentation

- **Latest:** https://kasir-barati.github.io/smart-novel-beatrice/latest/
- **All versions:** https://kasir-barati.github.io/smart-novel-beatrice/

Every release publishes a versioned copy — you can switch between versions from the picker in the top-right of any docs page.

The canonical SDL lives at [`docs/schema.graphql`](../docs/schema.graphql). Regenerate it locally with `make schema`.

## Running the Docker image

Images are published to Docker Hub as [`9109679196/smart-novel-beatrice`](https://hub.docker.com/r/9109679196/smart-novel-beatrice) on every `main` release.

### Quick start — against your own LLM backend

```bash
docker run --rm -p 3000:3000 \
  -e LLM__BASE_URL="https://api.openai.com/v1" \
  -e LLM__API_KEY="sk-..." \
  -e LLM__MODEL="gpt-4o-mini" \
  9109679196/smart-novel-beatrice:latest
```

The GraphQL endpoint is served at `http://localhost:3000/graphql`.

### With a local Ollama on the same host

```bash
# Requires Ollama running on the host with `ollama pull qwen2.5:3b` already done.
docker run --rm -p 3000:3000 \
  --add-host=host.docker.internal:host-gateway \
  -e LLM__BASE_URL="http://host.docker.internal:11434/v1" \
  -e LLM__API_KEY="ollama" \
  -e LLM__MODEL="qwen2.5:3b" \
  9109679196/smart-novel-beatrice:latest
```

### Sanity check

```bash
curl -sS http://localhost:3000/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"{ healthcheck { isRunning model version } }"}'
```

### Full stack (app + Ollama + OpenTelemetry + Jaeger) for local dev

Use the checked-in `compose.yml`:

```bash
docker compose up --build -d
# Jaeger UI: http://localhost:16686
# GraphQL:   http://localhost:3000/graphql
```

## Configuration

All configuration is via environment variables (see [`.env.example`](../.env.example)). Notable ones:

| Var                 | Purpose                                                                       |
| ------------------- | ----------------------------------------------------------------------------- |
| `LLM__BASE_URL`     | OpenAI-compatible endpoint (e.g. `https://api.openai.com/v1`, `http://ollama:11434/v1`) |
| `LLM__MODEL`        | Model name to request                                                         |
| `LLM__API_KEY`      | API key — any non-empty string for Ollama; real key for OpenAI/Together/etc.  |
| `LLM__TIMEOUT_MS`   | HTTP timeout for LLM calls (default `180000`)                                 |
| `PORT`              | HTTP port (default `3000`)                                                    |
| `LOGGING__MODE`     | `JSON` or `PLAIN_TEXT`                                                        |
| `OTEL__ENABLED`     | Set to `false` to disable OpenTelemetry export                                |
| `OTEL__EXPORTER_OTLP_ENDPOINT` | OTLP HTTP endpoint (e.g. `http://otel-collector:4318`)             |

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for local setup, project layout, and the testing philosophy.

## References

- https://dev.to/kasir-barati/does-pydantic-ais-structured-output-api-actually-work-against-ollamas-openai-compatible-endpoint-44aa
