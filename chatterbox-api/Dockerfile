FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

ARG CHATTERBOX_TTS_VERSION=0.1.7

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        git \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir \
    "chatterbox-tts==${CHATTERBOX_TTS_VERSION}" \
    --requirement requirements.txt

COPY app.py .

EXPOSE 8880

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8880", "--workers", "1"]
