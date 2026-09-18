FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --requirement requirements.txt

COPY app ./app

RUN useradd --create-home --uid 10001 --gid voice voice \
    && chown -R voice:voice /app

USER voice

CMD ["python", "-m", "app.agent", "start"]
