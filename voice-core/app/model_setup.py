import logging
import os
from urllib.parse import quote

import httpx

from app.logging_config import configure_logging


def model_url(base_url: str, model_id: str) -> str:
    return f"{base_url.rstrip('/')}/models/{quote(model_id, safe='')}"


def ensure_stt_model() -> None:
    base_url = os.getenv("STT_BASE_URL", "http://faster-whisper:8000/v1")
    model_id = os.getenv("STT_MODEL", "Systran/faster-whisper-small")
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    logger = logging.getLogger("stt-model-setup")
    url = model_url(base_url, model_id)

    with httpx.Client(timeout=None) as client:
        response = client.get(url)
        if response.status_code == 200:
            logger.info("stt_model_already_installed", extra={"model": model_id})
            return
        if response.status_code != 404:
            response.raise_for_status()

        logger.info("stt_model_download_started", extra={"model": model_id})
        response = client.post(url)
        response.raise_for_status()

        response = client.get(url)
        response.raise_for_status()
        logger.info("stt_model_ready", extra={"model": model_id})


if __name__ == "__main__":
    ensure_stt_model()
