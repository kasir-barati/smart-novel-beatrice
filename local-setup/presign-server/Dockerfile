FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir fastapi "uvicorn[standard]" minio

COPY server.py /app/server.py
WORKDIR /app

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=10s \
    CMD ["curl", "-fsS", "http://127.0.0.1:8002/health"]

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8002"]
