# Kept self-contained here so developers can work without cloning the model over and over again.

FROM ollama/ollama:0.17.7

ARG OLLAMA_MODEL=llama3.2:1b
ENV OLLAMA_MODEL=${OLLAMA_MODEL}
# CAUTION: 0.0.0.0 means Ollama listens on every network interface — required for the healthcheck and for the container to be reachable from a sibling container.
ENV OLLAMA_HOST=0.0.0.0
ENV OLLAMA_PORT=11434

# curl for build-time readiness checks + the runtime healthcheck.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

COPY --chmod=755 prepull-model.sh /usr/local/bin/prepull-model.sh
RUN /usr/local/bin/prepull-model.sh

COPY --chmod=755 healthcheck.sh /usr/local/bin/healthcheck.sh
HEALTHCHECK --interval=30s --timeout=5s --retries=5 --start-period=45s CMD ["/usr/local/bin/healthcheck.sh"]

# IMPORTANT: prepull-model.sh stops the daemon when it's done. We start a fresh one here so the container becomes usable.
CMD ["serve"]
