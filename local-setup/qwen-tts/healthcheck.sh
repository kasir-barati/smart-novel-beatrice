#!/bin/sh
set -eu

PORT="${QWEN_TTS_PORT:-8001}"

CODE="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/health")"

[ "$CODE" -eq 200 ]
