"""
Domain types for the TTS provider abstraction layer.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


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
