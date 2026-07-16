SHELL         := /bin/bash
.SHELLFLAGS   := -eu -o pipefail -c
.DEFAULT_GOAL := help

.ONESHELL:
.PHONY: help init start_dev test integration_test evals evals_baseline _run_evals schema lint_check lint clean

# ---- Configurable knobs -----------------------------------------------------
PORT      ?= 3000
IMAGE     ?= smart-novel-beatrice
TAG       ?= dev


## Show this help message
help:
	@echo "Makefile targets:"
	@echo ""
	@awk '/^## /{desc = substr($$0, 4)} /^[a-zA-Z_-]+:/{if (desc) {target = $$1; sub(/:.*/, "", target); printf "  make %-20s- %s\n", target, desc; desc = ""}}' $(MAKEFILE_LIST)
	@echo ""

## Initialize project (install deps, setup pre-commit, create .env)
init:
	@which uv > /dev/null || (echo "Error: uv is not installed. Please install uv: https://docs.astral.sh/uv/getting-started/installation/" && exit 1)
	uv venv .venv
	uv sync
	cp --update=none .env.example .env || true
	uv run pre-commit install

## Starts the app with auto-reload
start_dev:
	uv run uvicorn src.main:app --host 0.0.0.0 --port $(PORT) --reload

## Starts the app in production mode
start:
	uv run --no-sync python src/main.py

## Runs unit tests
test:
	export TESTS_START_TS=$$(date +%s)
	@echo "== running unit tests at $$(date -u +%Y-%m-%dT%H:%M:%SZ) =="
	uv run pytest src/ -v
	export TESTS_END_TS=$$(date +%s)
	@echo "== finished running unit tests at $$(date -u +%Y-%m-%dT%H:%M:%SZ) =="
	@echo "== unit tests took $$((TESTS_END_TS - TESTS_START_TS))s =="

## Run integration tests
integration_test:
	export TESTS_START_TS=$$(date +%s)
	@echo "== running integration tests at $$(date -u +%Y-%m-%dT%H:%M:%SZ) =="
	uv run pytest tests/ -v
	export TESTS_END_TS=$$(date +%s)
	@echo "== finished running integration tests at $$(date -u +%Y-%m-%dT%H:%M:%SZ) =="
	@echo "== integration tests took $$((TESTS_END_TS - TESTS_START_TS))s =="

## Discover and run every module's evals/run.py against the current prompts
evals:
	export TESTS_START_TS=$$(date +%s)
	@echo "== running evals at $$(date -u +%Y-%m-%dT%H:%M:%SZ) =="
	@$(MAKE) --no-print-directory _run_evals EVALS_ARGS=""
	export TESTS_END_TS=$$(date +%s)
	@echo "== finished running evals at $$(date -u +%Y-%m-%dT%H:%M:%SZ) =="
	@echo "== evals took $$((TESTS_END_TS - TESTS_START_TS))s =="

## Update the committed baseline scores after a deliberate quality change
evals_baseline:
	@$(MAKE) --no-print-directory _run_evals EVALS_ARGS="--update-baseline"

_run_evals:
	@shopt -s nullglob
	cp --update=none .env.example .env || true
	set -a; . ./.env; set +a
	files=(src/modules/*/evals/run.py)
	if [ $${#files[@]} -eq 0 ]; then
		echo "No eval suites found under src/modules/*/evals/run.py"
		exit 0
	fi
	echo "== starting ollama (compose) =="
	docker compose up -d --wait ollama
	trap 'echo "== stopping ollama =="; docker compose stop ollama >/dev/null' EXIT
	export LLM__BASE_URL="http://localhost:11434/v1"
	echo "== ollama diagnostics (model=$$LLM__MODEL) =="
	echo "-- ollama version --"
	curl -fsS http://localhost:11434/api/version || true; echo
	echo "-- ollama CLI version (inside container) --"
	docker compose exec -T ollama ollama --version || true
	echo "-- ollama registered models (name, digest, size, modified) --"
	curl -fsS http://localhost:11434/api/tags \
		| uv run python -c 'import json,sys; [print(m["name"], m.get("digest"), m.get("size"), m.get("modified_at")) for m in json.load(sys.stdin)["models"]]' || true
	echo "-- /api/show for $$LLM__MODEL --"
	curl -fsS -X POST http://localhost:11434/api/show -H 'Content-Type: application/json' -d "{\"name\":\"$$LLM__MODEL\"}" \
		| uv run python -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({"digest": d.get("digest"), "details": d.get("details"), "model_info_keys": sorted((d.get("model_info") or {}).keys())}, indent=2))' || true
	echo "== end diagnostics =="
	failed=()
	for f in "$${files[@]}"; do
		echo "== running $$f (LLM__BASE_URL=$$LLM__BASE_URL) =="
		if ! uv run python "$$f" $(EVALS_ARGS); then
			failed+=("$$f")
		fi
	done
	if [ $${#failed[@]} -ne 0 ]; then
		echo ""
		echo "== $${#failed[@]} eval suite(s) failed =="
		for f in "$${failed[@]}"; do echo "  - $$f"; done
		exit 1
	fi

## Export the GraphQL SDL to docs/schema.graphql (source of truth for API docs)
schema:
	@echo "== exporting GraphQL schema to docs/schema.graphql =="
	mkdir -p docs
	uv run strawberry export-schema src.schema:schema > docs/schema.graphql
	@echo "== wrote docs/schema.graphql ($$(wc -l < docs/schema.graphql) lines) =="
	uv run pre-commit run --files docs/schema.graphql

## Runs ruff linter on all files
lint_check:
	uv run ruff check .
	uv run python local-setup/scripts/check_private_imports.py

## Apply linter to all files
lint:
	uv run ruff format .
	uv run pyright src
	uv run ruff check --fix .
	uv run python local-setup/scripts/check_private_imports.py

## Remove build artefacts, caches, .venv, __pycache__
clean:
	rm -rf .venv build dist htmlcov .pytest_cache .ruff_cache .pyright .coverage .coverage.* coverage.xml *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
