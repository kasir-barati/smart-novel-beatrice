#!/bin/sh
set -eu

HOST="${OLLAMA_HOST:-127.0.0.1}"
PORT="${OLLAMA_PORT:-11434}"
MODEL="${OLLAMA_MODEL:-llama3.2:1b}"

# 1) API up?
if ! curl -fsS "http://${HOST}:${PORT}/api/version" >/dev/null; then
  exit 1
fi

# 2) Model registered locally?
if ! curl -fsS "http://${HOST}:${PORT}/api/tags" | grep -q "\"name\":\"${MODEL}\""; then
  exit 1
fi

# 3) /api/generate usable? (Minimal, cheap request; do not exercise the model.)
CODE="$(curl -sS -o /dev/null -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -X POST "http://${HOST}:${PORT}/api/generate" \
  -d "{\"model\":\"${MODEL}\",\"prompt\":\"ping\",\"stream\":false,\"options\":{\"num_predict\":1}}")"

[ "$CODE" -eq 200 ]
