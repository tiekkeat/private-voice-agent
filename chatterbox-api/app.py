import asyncio
import io
import os
import re
import wave
from contextlib import asynccontextmanager
from typing import Literal

import numpy as np
import torch
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field


SUPPORTED_LANGUAGES = {"en", "ms", "zh"}
MALAY_MARKERS = {
    "awak",
    "balik",
    "boleh",
    "dengan",
    "kalau",
    "kasih",
    "lah",
    "macam",
    "nak",
    "nanti",
    "saya",
    "sekarang",
    "sudah",
    "tak",
    "terima",
    "tidak",
    "untuk",
    "yang",
}
HAN_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
WORD_PATTERN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

model: ChatterboxMultilingualTTS | None = None
generation_lock = asyncio.Lock()


class SpeechRequest(BaseModel):
    input: str = Field(min_length=1, max_length=600)
    model: str = "chatterbox-multilingual-v3"
    voice: str = "en"
    response_format: Literal["pcm", "wav"] = "pcm"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)


def detect_language(text: str) -> str:
    if HAN_PATTERN.search(text):
        return "zh"
    words = {match.group(0).lower() for match in WORD_PATTERN.finditer(text)}
    return "ms" if words & MALAY_MARKERS else "en"


def pcm16_bytes(waveform: torch.Tensor) -> bytes:
    samples = waveform.detach().float().squeeze().cpu().numpy()
    return (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


def wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return output.getvalue()


def generate(text: str, language: str) -> tuple[bytes, int]:
    if model is None:
        raise RuntimeError("model is not ready")
    with torch.inference_mode():
        waveform = model.generate(text, language_id=language)
    return pcm16_bytes(waveform), model.sr


@asynccontextmanager
async def lifespan(_: FastAPI):
    global model
    device = os.getenv("CHATTERBOX_DEVICE", "cuda")
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CHATTERBOX_DEVICE=cuda but CUDA is unavailable")
    t3_model = os.getenv("CHATTERBOX_T3_MODEL", "v3")
    model = ChatterboxMultilingualTTS.from_pretrained(
        device=device,
        t3_model=t3_model,
    )
    yield
    model = None
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


app = FastAPI(title="Chatterbox OpenAI-compatible TTS", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    if model is None:
        raise HTTPException(status_code=503, detail="model is loading")
    return {"status": "ok", "model": "chatterbox-multilingual-v3"}


@app.get("/v1/models")
async def models() -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {
                "id": "chatterbox-multilingual-v3",
                "object": "model",
                "owned_by": "ResembleAI",
            }
        ],
    }


@app.post("/v1/audio/speech")
async def speech(request: SpeechRequest) -> Response:
    if request.model != "chatterbox-multilingual-v3":
        raise HTTPException(status_code=400, detail="unsupported model")
    language = request.voice.lower() if request.voice else detect_language(request.input)
    if language not in SUPPORTED_LANGUAGES:
        language = detect_language(request.input)

    async with generation_lock:
        try:
            pcm, sample_rate = await asyncio.to_thread(
                generate, request.input, language
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    if request.response_format == "wav":
        return Response(wav_bytes(pcm, sample_rate), media_type="audio/wav")
    return Response(
        pcm,
        media_type="audio/pcm",
        headers={
            "X-Audio-Sample-Rate": str(sample_rate),
            "X-Audio-Channels": "1",
            "X-Audio-Sample-Width": "2",
        },
    )
