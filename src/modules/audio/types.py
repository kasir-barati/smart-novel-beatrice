"""
Domain types for the TTS provider abstraction layer.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Voice(BaseModel):
    name: str = Field(
        description="Provider-specific voice identifier to pass back into `synthesize`."
    )
    language_codes: list[str] = Field(
        default_factory=list,
        description=(
            'BCP-47 language tags this voice supports (e.g. "en-US"). Only populated for '
            "Gemini-TTS — Qwen3-TTS's third-party inference APIs report no per-voice language "
            "metadata, so this is always empty there."
        ),
    )


class SynthesizedAudio(BaseModel):
    """
    Result of a `synthesize` call. `file_path` is a local file — this abstraction never
    touches an object store or presigned URL directly. Uploading it is the caller's
    responsibility, against any S3-compatible presigned URL (no `boto3`, just a PUT).
    """

    file_path: Path = Field(description="Absolute path to the generated audio file on local disk.")


class GenerateAudioJob(BaseModel):
    """
    A `generateAudio` job message as consumed from the queue. Field names use the camelCase
    aliases the `generateAudio` mutation publishes (`src/modules/audio/resolver.py`), since the
    message body is that mutation's input verbatim plus `jobId`.
    """

    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(alias="jobId")
    text: str
    voice: str
    gen_upload_url: str = Field(alias="genUploadUrl")
    status_callback_url: str = Field(alias="statusCallbackUrl")
    instruct: str | None = Field(
        default=None,
        description="Qwen3-TTS style guide, absent on messages published before this field existed.",
    )
    client_context_id: str | None = Field(
        default=None,
        alias="clientContextId",
        description="Opaque caller-supplied value, echoed verbatim on every callback.",
    )


class SynthesizeErrorCode(StrEnum):
    """Error codes reported to `statusCallbackUrl` on a `{status: "failed"}` update."""

    TTS_PROVIDER_ERROR = "TTS_PROVIDER_ERROR"
    """Synthesis (the TTS provider call) failed."""

    UPLOAD_ERROR = "UPLOAD_ERROR"
    """Fetching a presigned URL from `genUploadUrl`, or the PUT to it, failed."""
