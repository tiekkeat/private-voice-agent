# Realtime Voice Gateway

Self-hosted realtime voice assistant gateway built around LiveKit Agents, Silero VAD, Speaches/faster-whisper, an OpenAI-compatible streaming LLM, and Kokoro-FastAPI.

This repository is at the first implementation milestone: the deployment and application skeleton is in place, with CPU/GPU variants, isolated per-user rooms, token issuance, health reporting, a minimal browser client, and LiveKit-managed interruption/cancellation.

## Architecture

```text
Browser ──HTTPS/WSS── Caddy ── LiveKit ── Voice Core
                                      ├── Speaches / faster-whisper
                                      ├── OpenAI-compatible LLM
                                      └── Kokoro-FastAPI
```

Only Caddy and LiveKit's WebRTC media ports are exposed to the LAN. Redis, STT, TTS, the token API, and the frontend container stay on the private Compose network.

## Prerequisites

- Linux host with Docker Engine and Docker Compose v2
- A LAN-resolvable hostname (the examples use `voice.local`)
- Firewall access from LAN clients to TCP 80, 443, 7881 and UDP 50000-50100
- An OpenAI-compatible API endpoint and a streaming text model
- GPU mode only: a working NVIDIA driver and NVIDIA Container Toolkit

Before GPU deployment, verify the container runtime:

```bash
docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi
```

## Configure

Create the common and mode-specific environment files:

```bash
cp .env.example .env
cp .env.cpu.example .env.cpu
cp .env.gpu.example .env.gpu
```

Edit `.env` and set at least:

- `VOICE_HOST`: LAN DNS name used in the browser
- `LIVEKIT_NODE_IP`: LAN IP of the Linux VM; this is advertised to WebRTC clients
- `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET`: long, randomly generated credentials
- `PUBLIC_LIVEKIT_URL`: normally `wss://<VOICE_HOST>/livekit`
- `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`
- `TTS_VOICE` and `TTS_CHINESE_VOICE` select the English and Mandarin Kokoro voices
- `STT_LANGUAGE`: `auto` for bilingual use, `zh` to lock Mandarin, or `en` to lock English

The LLM key is used only by the server-side worker and is never returned to the browser, following the [official OpenAI API authentication guidance](https://developers.openai.com/api/reference/overview#authentication).

### Turn detector choice

`TURN_DETECTOR_MODE=v1-mini` enables LiveKit's current audio turn detector. In LiveKit Agents 1.8.2, this model runs locally by design and keeps roughly 108 MB of weights resident in the worker process.

For the lowest-resource fallback, set `TURN_DETECTOR_MODE=vad`. Silero still provides fast speech-start detection and barge-in, but end-of-turn behavior is less natural.

Interruption defaults require 0.8 seconds of detected speech and at least one
recognized word before stopping playback. Tune `INTERRUPTION_MIN_DURATION` and
`INTERRUPTION_MIN_WORDS` if the microphone environment is unusually noisy.

## Run

CPU mode:

```bash
docker compose \
  --env-file .env \
  --env-file .env.cpu \
  -f docker-compose.yml \
  -f docker-compose.cpu.yml \
  up -d --build
```

GPU mode:

```bash
docker compose \
  --env-file .env \
  --env-file .env.gpu \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  up -d --build
```

For a complete host preparation, transfer, firewall, GPU validation, deployment,
TLS trust, and rollback procedure, see [Linux NVIDIA GPU deployment](docs/linux-gpu-deployment.md).

Model images and weights are large. The first startup may take several minutes; follow it with:

```bash
docker compose logs -f faster-whisper kokoro voice-core
```

## LAN TLS trust

Caddy uses its internal CA so browsers can grant microphone access over HTTPS. After Caddy starts, export its root certificate:

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
```

Install `caddy-root.crt` as a trusted root CA on each client device, ensure `VOICE_HOST` resolves to `LIVEKIT_NODE_IP`, then open `https://<VOICE_HOST>`.

Do not distribute the Caddy private key. Back up the `caddy-data` volume if you want deployed client trust to survive a full volume loss.

## Verify

```bash
curl --fail --cacert ./caddy-root.crt "https://${VOICE_HOST}/api/health"
docker compose ps
docker compose logs --tail=100 voice-core
```

Expected health output reports the configured CPU/GPU mode, STT compute type, LLM backend, TTS device, and dependency availability. It does not silently claim GPU operation when CPU settings are active.

Then test from a second LAN device:

1. Open the HTTPS site and click **Connect microphone**.
2. Speak in English, Mandarin, Malay, and mixed-language utterances.
3. Interrupt a long assistant response while it is speaking.
4. Confirm audio stops, the new transcript appears, and the next response addresses the interruption.
5. Repeat in a second browser; each token creates a separate room and conversation.

## Development checks

```bash
python -m compileall voice-core/app voice-core/tests
docker compose --env-file .env.example --env-file .env.cpu.example \
  -f docker-compose.yml -f docker-compose.cpu.yml config --quiet
```

For Python tests, create a virtual environment and install `voice-core/requirements-dev.txt`, then run `pytest voice-core/tests` with `PYTHONPATH=voice-core`.

## Implementation notes

- LiveKit `AgentSession` owns streamed STT → LLM → TTS orchestration, phrase chunking, playback tracking, and cancellation. This preserves only played assistant speech when an interruption occurs.
- `OpenAICompatibleBackend` is the small backend boundary that Objective 2 can replace with an OpenClaw adapter.
- Kokoro is connected through its OpenAI-compatible streaming speech endpoint using WAV/PCM, avoiding an MP3 decode stage.
- Reply text containing Han characters is routed to `TTS_CHINESE_VOICE`; other replies use `TTS_VOICE`.
- Speaches provides the OpenAI-compatible faster-whisper service. The stable `0.8.3` CPU and CUDA 12.6.3 image variants are pinned.
- The default CPU profile uses multilingual Whisper Small for lower latency; a larger model can be selected with `STT_MODEL` when accuracy is more important.
- Container logs are rotated at 10 MB × 3 files.

## Persistence and backups

Back up these named volumes:

- `redis-data` (ephemeral coordination; useful but not a conversation-history database)
- `whisper-models` (downloaded model cache; recoverable by re-downloading)
- `caddy-data` and `caddy-config` (local CA and certificate state)

Also back up `.env` securely. It contains LiveKit and LLM secrets and must never be committed. Conversation history is intentionally in memory and is lost when the worker restarts.

Before upgrading LiveKit, LiveKit Agents, Speaches, or Kokoro, review their release notes, back up the Caddy volumes, and validate one- and two-user barge-in behavior again.

## Next milestone

The scaffold still needs deployment-host integration testing before Objective 1 can be called complete. The next work should:

1. Boot the CPU stack on the target Linux VM and verify WebRTC candidates from a second LAN device.
2. Exercise English/Mandarin/Malay mixed-language transcription and tune Speaches model settings.
3. Run the GPU stack after `nvidia-smi` validation.
4. Measure one- and two-user speech-end-to-first-audio and interruption latency (p50/p95).
