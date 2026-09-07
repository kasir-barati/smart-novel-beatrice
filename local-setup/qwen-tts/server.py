"""
OpenAI-compatible TTS server backed by Qwen3-TTS, matching the contract
`Qwen3TtsProvider` (`src/modules/audio/qwen_provider.py`) already expects:

- `GET /v1/voices`             -> {"voices": [{"name": ...}, ...]}
- `POST /v1/audio/speech`      -> {"model", "input", "voice", "instruct"?} -> raw audio bytes

`_VOICES` maps the fixed voice names this server exposes to one of Qwen3-TTS's built-in
preset speakers, synthesized via `generate_custom_voice`. This (rather than
`generate_voice_clone`) is what lets `instruct` (natural-language tone/style/emotion
guidance) combine with a consistent named voice in one call.
"""

import io
import os

import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from qwen_tts import Qwen3TTSModel


MODEL_ID = os.environ.get("QWEN_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")
DEVICE = os.environ.get("QWEN_TTS_DEVICE", "cpu")
PORT = int(os.environ.get("QWEN_TTS_PORT", "8001"))
LANGUAGE = os.environ.get("QWEN_TTS_LANGUAGE", "English")

_VOICES = {"default": "Ryan"}

app = FastAPI()
model: Qwen3TTSModel | None = None


class SpeechRequest(BaseModel):
    model: str
    input: str
    voice: str
    instruct: str | None = None


@app.on_event("startup")
def load_model() -> None:
    global model
    model = Qwen3TTSModel.from_pretrained(
        MODEL_ID,
        device_map=DEVICE,
        dtype=torch.bfloat16 if DEVICE != "cpu" else torch.float32,
    )


@app.get("/health")
def health() -> dict[str, bool]:
    return {"loaded": model is not None}


@app.get("/v1/voices")
def list_voices() -> dict[str, list[dict[str, str]]]:
    return {"voices": [{"name": name} for name in _VOICES]}


@app.post("/v1/audio/speech")
def synthesize(request: SpeechRequest) -> Response:
    speaker = _VOICES.get(request.voice)
    if speaker is None:
        raise HTTPException(status_code=422, detail=f"Unknown voice: {request.voice}")

    wavs, sample_rate = model.generate_custom_voice(
        text=request.input,
        language=LANGUAGE,
        speaker=speaker,
        instruct=request.instruct,
    )
    buffer = io.BytesIO()
    sf.write(buffer, wavs[0], sample_rate, format="WAV")
    return Response(content=buffer.getvalue(), media_type="audio/wav")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
