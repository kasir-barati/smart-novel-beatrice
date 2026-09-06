#!/bin/sh
set -eu

python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('${QWEN_TTS_MODEL}')
"
