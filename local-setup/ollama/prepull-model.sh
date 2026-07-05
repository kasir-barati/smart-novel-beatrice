#!/bin/sh
#
# Pull the target Ollama model at *image build time* so container startup is
# instant and offline-friendly. Runs a temporary ollama daemon, waits for it to
# accept requests, pulls the model, then shuts the daemon back down.
#
# Adapted from ../../../smart-novel/local-setup/ollama/prepull-model.sh.

set -eu

HOST="${OLLAMA_HOST:-127.0.0.1}"
PORT="${OLLAMA_PORT:-11434}"
MODEL="${OLLAMA_MODEL:-llama3.2:1b}"
READY_TRIES="${OLLAMA_READY_TRIES:-60}"
READY_SLEEP="${OLLAMA_READY_SLEEP:-1}"

log() { printf '%s\n' "$*" >&2; }

cleanup() {
  if [ -n "${PID:-}" ] && kill -0 "$PID" 2>/dev/null; then
    kill -TERM "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

log "Starting ollama daemon for build-time model pull..."
ollama serve >/tmp/ollama-build.log 2>&1 &
PID=$!

i=0
while [ "$i" -lt "$READY_TRIES" ]; do
  if curl -fsS "http://${HOST}:${PORT}/api/version" >/dev/null; then
    break
  fi
  i=$((i+1))
  sleep "$READY_SLEEP"
done

if ! curl -fsS "http://${HOST}:${PORT}/api/version" >/dev/null; then
  log "Ollama daemon did not become ready during build."
  log "Last log lines:"; tail -n 120 /tmp/ollama-build.log || true
  exit 1
fi

log "Daemon is ready. Pulling model: ${MODEL}"
ollama pull "${MODEL}"

log "Listing models:"; ollama list || true
log "Done."
