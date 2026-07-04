# smart-novel-beatrice

Python service exposing a **GraphQL API** for LLM-powered features used by [smart-novel](https://github.com/kasir-barati/smart-novel):

The service is **model-provider-agnostic**: it talks to any OpenAI-compatible HTTP endpoint (Ollama, vLLM, OpenAI, Together, Groq, …) via [`pydantic-ai`](https://ai.pydantic.dev). Prompts, schemas, agents, and evals live inside this repo — model choice is a config change.

## Requirements

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- Docker
- An OpenAI-compatible LLM backend (Ollama by default; see `.env.example`)

## Quickstart

```bash
make init
```

Every dev and CI command goes through `make`.

## Configuration

All configuration is via environment variables (see `.env.example`). Notable ones:

| Var                 | Purpose                                                                       |
| ------------------- | ----------------------------------------------------------------------------- |
| `LLM_BASE_URL`      | OpenAI-compatible endpoint (e.g. `http://ollama:11434/v1`)                    |
| `LLM_MODEL`         | Default model name                                                            |
| `LLM_API_KEY`       | API key — any non-empty string for Ollama; real key for OpenAI/Together/etc.  |
| `PORT`              | HTTP port (default `3000`)                                                    |
| `LOGGING_MODE`      | `JSON` or `PRETTY`                                                            |
| `OTEL_*`            | OpenTelemetry export settings                                                 |

## Status

Bootstrap / scaffolding phase — no endpoints implemented yet. Track progress against `smart-novel-beatrice-plan.md`.
