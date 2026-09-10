"""
DashScope-compatible TTS server backed by Qwen3-TTS, matching the contract
`Qwen3TtsProvider` (`src/modules/audio/qwen_provider.py`) expects from the real
Alibaba Cloud DashScope API:

- `POST /api/v1/services/aigc/multimodal-generation/generation`
  -> {"model", "input": {"text", "voice", "language_type"}, "instructions"?}
  -> {"output": {"audio": {"url": "..."}}}
- `GET /files/{filename}` -> raw audio bytes, serving what the POST above just wrote.

DashScope returns a URL rather than audio bytes directly, so the synthesized audio is
written to a local temp file and served back from `/files/{filename}` — the URL points
at this same server, built from the incoming request's own host so it works whether
that's `qwen-tts:8001` (compose network) or `localhost:8001` (host machine).

`_VOICES` maps the fixed voice names this server exposes to one of Qwen3-TTS's built-in
preset speakers, synthesized via `generate_custom_voice`. This (rather than
`generate_voice_clone`) is what lets `instructions` (natural-language tone/style/emotion
guidance) combine with a consistent named voice in one call.
"""

import os
import tempfile
import uuid
from pathlib import Path

import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from qwen_tts import Qwen3TTSModel


MODEL_ID = os.environ.get("QWEN_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")
DEVICE = os.environ.get("QWEN_TTS_DEVICE", "cpu")
PORT = int(os.environ.get("QWEN_TTS_PORT", "8001"))

_VOICES = {"default": "Ryan"}
_OUTPUT_DIR = Path(tempfile.gettempdir()) / "qwen-tts-shim-audio"

app = FastAPI()
model: Qwen3TTSModel | None = None


class SynthesizeInput(BaseModel):
    text: str
    voice: str
    language_type: str


class GenerationRequest(BaseModel):
    model: str
    input: SynthesizeInput
    instructions: str | None = None


@app.on_event("startup")
def load_model() -> None:
    global model
    model = Qwen3TTSModel.from_pretrained(
        MODEL_ID,
        device_map=DEVICE,
        dtype=torch.bfloat16 if DEVICE != "cpu" else torch.float32,
    )
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"loaded": model is not None}


@app.post("/api/v1/services/aigc/multimodal-generation/generation")
def generate(
    request: GenerationRequest, http_request: Request
) -> dict[str, dict[str, dict[str, str]]]:
    speaker = _VOICES.get(request.input.voice)
    if speaker is None:
        raise HTTPException(status_code=422, detail=f"Unknown voice: {request.input.voice}")

    wavs, sample_rate = model.generate_custom_voice(
        text=request.input.text,
        language=request.input.language_type,
        speaker=speaker,
        instruct=request.instructions,
    )

    filename = f"{uuid.uuid4()}.wav"
    sf.write(str(_OUTPUT_DIR / filename), wavs[0], sample_rate, format="WAV")

    audio_url = str(http_request.base_url.replace(path=f"/files/{filename}"))
    return {"output": {"audio": {"url": audio_url}}}


@app.get("/files/{filename}")
def get_file(filename: str) -> FileResponse:
    file_path = _OUTPUT_DIR / filename
    if file_path.parent != _OUTPUT_DIR or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path, media_type="audio/wav")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
