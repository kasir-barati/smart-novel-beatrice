# Kept self-contained here so developers can work without downloading the model over and over again.

FROM python:3.11-slim

ARG QWEN_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
ENV QWEN_TTS_MODEL=${QWEN_TTS_MODEL}
ENV QWEN_TTS_DEVICE=cpu
ENV QWEN_TTS_PORT=8001
# Cache HF downloads in the image layer instead of re-fetching them into a throwaway container home dir.
ENV HF_HOME=/root/.cache/huggingface

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl libsndfile1 sox && \
    rm -rf /var/lib/apt/lists/*

# torch and torchaudio must resolve in the same pip invocation: qwen-tts depends on
# torchaudio, and a separate later `pip install qwen-tts` would let it pull torchaudio's
# default (CUDA) wheel from PyPI, mismatched against the CPU-only torch installed here —
# torchaudio's compiled extension then fails to load (`libcudart.so.13` not found).
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    torch \
    torchaudio \
    qwen-tts \
    fastapi \
    uvicorn[standard] \
    soundfile \
    huggingface_hub

COPY --chmod=755 prepull-model.sh /usr/local/bin/prepull-model.sh
RUN /usr/local/bin/prepull-model.sh

COPY --chmod=755 healthcheck.sh /usr/local/bin/healthcheck.sh
COPY server.py /app/server.py
WORKDIR /app

EXPOSE ${QWEN_TTS_PORT}

HEALTHCHECK --interval=30s --timeout=5s --retries=5 --start-period=60s CMD ["/usr/local/bin/healthcheck.sh"]

CMD ["python3", "server.py"]
