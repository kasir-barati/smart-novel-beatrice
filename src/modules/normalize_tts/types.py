"""
Domain types for the ``normalizeTextForTts`` feature.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class NormalizedText(BaseModel):
    normalized_text: str = Field(
        description=(
            "The input text rewritten for TTS: interjections canonicalised, "
            "stutters expanded, silent-dialogue cues clarified, and excessive "
            "repetition collapsed. Narrative meaning is preserved exactly."
        ),
    )
