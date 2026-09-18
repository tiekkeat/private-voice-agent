import asyncio
import re
import uuid
from datetime import timedelta
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException
from livekit import api
from pydantic import BaseModel, Field

from app.config import get_settings
from app.logging_config import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="Realtime Voice Gateway", version="0.1.0")


class TokenRequest(BaseModel):
    display_name: str = Field(default="Guest", min_length=1, max_length=64)


class TokenResponse(BaseModel):
    token: str
    url: str
    room: str
    identity: str


def _safe_label(value: str) -> str:
    label = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-")
    return label[:32] or "guest"


@app.post("/token", response_model=TokenResponse)
async def create_token(request: TokenRequest) -> TokenResponse:
    suffix = uuid.uuid4().hex[:12]
    label = _safe_label(request.display_name)
    room = f"voice-{suffix}"
    identity = f"{label}-{suffix}"

    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(request.display_name.strip())
        .with_ttl(timedelta(minutes=15))
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .to_jwt()
    )
    return TokenResponse(
        token=token,
        url=settings.public_livekit_url,
        room=room,
        identity=identity,
    )


async def _probe(client: httpx.AsyncClient, name: str, url: str) -> tuple[str, str]:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return name, "ok"
    except (httpx.HTTPError, OSError):
        return name, "unavailable"


@app.get("/health")
async def health() -> dict[str, object]:
    async with httpx.AsyncClient(timeout=3.0) as client:
        results = dict(
            await asyncio.gather(
                _probe(
                    client,
                    "stt",
                    f"{settings.stt_base_url}/models/{quote(settings.stt_model, safe='')}",
                ),
                _probe(client, "tts", settings.tts_base_url + "/models"),
            )
        )

    status = "ok" if all(value == "ok" for value in results.values()) else "degraded"
    return {
        "status": status,
        "livekit": "configured",
        "stt": {
            "status": results["stt"],
            "device": settings.stt_device,
            "compute_type": settings.stt_compute_type,
            "model": settings.stt_model,
        },
        "llm": {"status": "configured", "backend": "openai_compatible"},
        "tts": {
            "status": results["tts"],
            "device": settings.tts_device,
            "model": settings.tts_model,
        },
        "turn_detector": settings.turn_detector_mode,
        "deployment_mode": settings.deployment_mode,
    }


@app.get("/ready")
async def ready() -> dict[str, str]:
    report = await health()
    if report["status"] != "ok":
        raise HTTPException(status_code=503, detail=report)
    return {"status": "ready"}
