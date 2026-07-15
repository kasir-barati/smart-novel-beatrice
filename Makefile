SHELL         := /usr/bin/env bash
.SHELLFLAGS   := -eu -o pipefail -c
.DEFAULT_GOAL := help

.PHONY: help init start_dev test integration_test evals evals_baseline _run_evals lint_check lint clean

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
	@echo "== running unit tests at $$(date -u +%Y-%m-%dT%H:%M:%SZ) =="
	uv run pytest src/ -v
	@echo "== finished running unit tests at $$(date -u +%Y-%m-%dT%H:%M:%SZ) =="

## Run integration tests
integration_test:
	@echo "== running integration tests at $$(date -u +%Y-%m-%dT%H:%M:%SZ) =="
	uv run pytest tests/ -v
	@echo "== finished running integration tests at $$(date -u +%Y-%m-%dT%H:%M:%SZ) =="

## Discover and run every module's evals/run.py against the current prompts
evals:
	@echo "== running evals at $$(date -u +%Y-%m-%dT%H:%M:%SZ) =="
	@$(MAKE) --no-print-directory _run_evals EVALS_ARGS=""
	@echo "== finished running evals at $$(date -u +%Y-%m-%dT%H:%M:%SZ) =="

## Update the committed baseline scores after a deliberate quality change
evals_baseline:
	@$(MAKE) --no-print-directory _run_evals EVALS_ARGS="--update-baseline"

_run_evals:
	@set -u -o pipefail; \
	shopt -s nullglob; \
	files=(src/modules/*/evals/run.py); \
	if [ $${#files[@]} -eq 0 ]; then \
		echo "No eval suites found under src/modules/*/evals/run.py"; \
		exit 0; \
	fi; \
	echo "== starting ollama (compose) =="; \
	docker compose up -d --wait ollama; \
	trap 'echo "== stopping ollama =="; docker compose stop ollama >/dev/null' EXIT; \
	export LLM__BASE_URL="http://localhost:11434/v1"; \
	failed=(); \
	for f in "$${files[@]}"; do \
		echo "== running $$f (LLM__BASE_URL=$$LLM__BASE_URL) =="; \
		if ! uv run python "$$f" $(EVALS_ARGS); then \
			failed+=("$$f"); \
		fi; \
	done; \
	if [ $${#failed[@]} -ne 0 ]; then \
		echo ""; \
		echo "== $${#failed[@]} eval suite(s) failed =="; \
		for f in "$${failed[@]}"; do echo "  - $$f"; done; \
		exit 1; \
	fi

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
