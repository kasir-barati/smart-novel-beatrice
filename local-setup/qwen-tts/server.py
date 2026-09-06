"""
OpenAI-compatible TTS server backed by Qwen3-TTS, matching the contract
`Qwen3TtsProvider` (`src/modules/audio/qwen_provider.py`) already expects:

- `GET /v1/voices`             -> {"voices": [{"name": ...}, ...]}
- `POST /v1/audio/speech`      -> {"model", "input", "voice"} -> raw audio bytes

Qwen3-TTS-12Hz-0.6B-Base has no built-in named-voice concept — it clones a voice
from a reference clip. `_VOICES` maps the fixed voice names this server exposes
to the reference clip/text each one clones from.
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


MODEL_ID = os.environ.get("QWEN_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-Base")
DEVICE = os.environ.get("QWEN_TTS_DEVICE", "cpu")
PORT = int(os.environ.get("QWEN_TTS_PORT", "8001"))
LANGUAGE = os.environ.get("QWEN_TTS_LANGUAGE", "English")

_VOICES = {
    "default": {
        "ref_audio": "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-TTS-Repo/clone.wav",
        "ref_text": (
            "Okay. Yeah. I resent you. I love you. I respect you. But you know what? You blew it!"
        ),
    }
}

app = FastAPI()
model: Qwen3TTSModel | None = None


class SpeechRequest(BaseModel):
    model: str
    input: str
    voice: str


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
    voice = _VOICES.get(request.voice)
    if voice is None:
        raise HTTPException(status_code=422, detail=f"Unknown voice: {request.voice}")

    wavs, sample_rate = model.generate_voice_clone(
        text=request.input,
        language=LANGUAGE,
        ref_audio=voice["ref_audio"],
        ref_text=voice["ref_text"],
    )
    buffer = io.BytesIO()
    sf.write(buffer, wavs[0], sample_rate, format="WAV")
    return Response(content=buffer.getvalue(), media_type="audio/wav")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
