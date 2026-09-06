"""
Stand-in for a client's `genUploadUrl` endpoint, backed by real MinIO.

Beatrice's worker POSTs here expecting `{"url": "<presigned-url>"}`
(see `src/modules/audio/worker.py::_fetch_presigned_upload_url`), then PUTs the
generated audio to that URL. Every call mints a fresh presigned PUT URL for a
new object key, matching how a real client would.
"""

import os
import uuid
from datetime import timedelta

from fastapi import FastAPI
from minio import Minio


MINIO_ENDPOINT = os.environ["MINIO_ENDPOINT"]
MINIO_ACCESS_KEY = os.environ["MINIO_ACCESS_KEY"]
MINIO_SECRET_KEY = os.environ["MINIO_SECRET_KEY"]
MINIO_BUCKET = os.environ["MINIO_BUCKET"]

app = FastAPI()
# region must be explicit: without it, the SDK looks the region up over HTTP, and
# the "minio" alias only resolves inside the docker network, not from callers of this API.
client = Minio(
    endpoint=MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False,
    region="us-east-1",
)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/presign")
def presign() -> dict[str, str]:
    object_name = f"{uuid.uuid4()}.wav"
    url = client.presigned_put_object(MINIO_BUCKET, object_name, expires=timedelta(minutes=10))
    return {"url": url}
