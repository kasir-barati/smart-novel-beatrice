# --------------------------------------------------------------
# ---------- Builder Stage -------------------------------------
# --------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /uvx /usr/local/bin/

ENV UV_PROJECT_ENVIRONMENT=/app/.venv

# `copy` link mode: safe across bind mounts / different filesystems.
ENV UV_LINK_MODE=copy

# Compiles Python source files (.py) into Python bytecode files (__pycache__/*.pyc) immediately after installation.
ENV UV_COMPILE_BYTECODE=1

# Never let uv download a different Python at build time.
ENV UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY src ./src
RUN uv sync --frozen --no-dev

# --------------------------------------------------------------
# ---------- Runtime Stage -------------------------------------
# --------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
EXPOSE 3000
ENV PORT=3000
ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid 1000 --home /app --no-create-home app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/src /app/src
COPY --from=builder --chown=app:app /app/pyproject.toml /app/pyproject.toml

USER app

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS -H "Content-Type: application/json" \
        --data '{"query":"{ healthcheck { isRunning } }"}' \
        "http://localhost:${PORT}/graphql" \
        | grep -Eq '"isRunning"[[:space:]]*:[[:space:]]*true' || exit 1

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "3000"]
