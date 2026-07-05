SHELL         := /usr/bin/env bash
.SHELLFLAGS   := -eu -o pipefail -c
.DEFAULT_GOAL := help

.PHONY: help init start_dev test integration_test evals evals_baseline lint_check lint clean

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
	uv run pytest src/ -v

## Run integration tests
integration_test:
	uv run pytest tests/ -v

## Discover and run every module's evals/run.py against the current prompts
evals:
	@set -e; \
	shopt -s nullglob; \
	files=(src/modules/*/evals/run.py); \
	if [ $${#files[@]} -eq 0 ]; then \
		echo "No eval suites found under src/modules/*/evals/run.py"; \
		exit 0; \
	fi; \
	for f in "$${files[@]}"; do \
		echo "== running $$f =="; \
		uv run python "$$f"; \
	done

## Update the committed baseline scores after a deliberate quality change
evals_baseline:
	@set -e; \
	shopt -s nullglob; \
	files=(src/modules/*/evals/run.py); \
	if [ $${#files[@]} -eq 0 ]; then \
		echo "No eval suites found under src/modules/*/evals/run.py"; \
		exit 0; \
	fi; \
	for f in "$${files[@]}"; do \
		echo "== baselining $$f =="; \
		uv run python "$$f" --update-baseline; \
	done

## Runs ruff linter on all files
lint_check:
	uv run ruff check .

## Apply linter to all files
lint:
	uv run ruff format .
	uv run pyright src
	uv run ruff check --fix .

## Remove build artefacts, caches, .venv, __pycache__
clean:
	rm -rf .venv build dist htmlcov .pytest_cache .ruff_cache .pyright .coverage .coverage.* coverage.xml *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
