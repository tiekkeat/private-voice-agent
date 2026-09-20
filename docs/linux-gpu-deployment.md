# Linux NVIDIA GPU deployment

This guide moves the voice gateway to a single x86_64 Ubuntu 22.04 or 24.04
Docker host with one NVIDIA GPU. It assumes LAN access, Docker Compose v2, and
the repository's Caddy-managed local TLS. Internet-facing LiveKit deployments
need public-IP/ICE/TURN configuration beyond this guide.

## 1. Prepare the Linux host

Install a supported NVIDIA driver through Ubuntu's package manager, reboot if
required, and confirm the host can see the GPU:

```bash
nvidia-smi
```

Install Docker Engine and the Compose plugin from Docker's official apt
repository. Follow the current steps at:

- https://docs.docker.com/engine/install/ubuntu/

Verify Docker itself before adding GPU support:

```bash
sudo docker run --rm hello-world
sudo docker compose version
```

Install NVIDIA Container Toolkit from NVIDIA's production repository, then
configure the Docker runtime:

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends ca-certificates curl gnupg2

curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -sL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Confirm a container can use the GPU. The Qwen image uses CUDA 12.8; on a Tesla
T4, a current data-center driver with CUDA 12 compatibility is required. Check
the `CUDA Version` shown by `nvidia-smi`, then run:

```bash
sudo docker run --rm --gpus all \
  nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi
```

Docker's Compose GPU syntax requires `capabilities: [gpu]`; the supplied GPU
override already includes it for both Qwen3-ASR and Chatterbox.

## 2. Transfer the repository

Preferred method when the repository has been pushed to a private Git remote:

```bash
sudo install -d -o "$USER" -g "$USER" /opt/custom-voice-agent
git clone YOUR_PRIVATE_REPOSITORY_URL /opt/custom-voice-agent
cd /opt/custom-voice-agent
```

Without a remote, transfer the tracked files from the Mac. Run this on the Mac,
replacing the destination:

```bash
rsync -a --delete --exclude='.git' --exclude='.env' \
  --exclude='caddy-root.crt' \
  '/Users/ctkeat/Desktop/custom voice agent/' \
  user@linux-host:/opt/custom-voice-agent/
```

Do not copy Docker Desktop's named-volume directories. Whisper weights are
recoverable and will download into a native Linux Docker volume on first start.

## 3. Configure the Linux deployment

On the Linux host:

```bash
cd /opt/custom-voice-agent
cp .env.example .env
cp .env.gpu.example .env.gpu
chmod 600 .env .env.gpu
```

Edit `.env` and set these values:

```dotenv
VOICE_HOST=voice.local
BIND_ADDRESS=0.0.0.0
LIVEKIT_NODE_IP=192.168.1.50
PUBLIC_LIVEKIT_URL=wss://voice.local/livekit
LIVEKIT_API_KEY=generate-a-new-value
LIVEKIT_API_SECRET=generate-at-least-32-random-characters
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=set-the-server-side-key
LLM_MODEL=gpt-5.4-mini
```

Use the Linux host's real LAN IP for `LIVEKIT_NODE_IP`. Ensure `VOICE_HOST`
resolves to that IP from every client, using local DNS or client hosts files.
Generate new LiveKit credentials rather than publishing them in Git.

The supplied `.env.gpu` is tuned for one 16 GB Tesla T4. It selects
Qwen3-ASR-1.7B in float16, caps vLLM at 52% of GPU memory, and selects
Chatterbox Multilingual V3 for English, Mandarin, and Malay output:

```dotenv
STT_MODEL=Qwen/Qwen3-ASR-1.7B
STT_MODEL_SETUP_ENABLED=false
QWEN_GPU_MEMORY_UTILIZATION=0.52
TTS_MODEL=chatterbox-multilingual-v3
TTS_VOICE=en
TTS_CHINESE_VOICE=zh
TTS_MALAY_VOICE=ms
SYSTEM_PROMPT=You are a concise friendly voice assistant. Naturally follow the user's mix of Malaysian English Mandarin Chinese and Malay.
```

Do not add the optional Qwen forced aligner on the T4; the voice gateway does
not need timestamps, and the extra model would consume VRAM needed by TTS.

For Malaysian English/Mandarin/Malay conversations, keep `STT_LANGUAGE=auto`.
Use `zh`, `en`, or `ms` only for a session that must be locked to one language.
Qwen supports all three languages, but very short sounds still contain little
language evidence, so the interruption thresholds remain important.

The default interruption settings filter brief non-speech sounds while keeping
barge-in enabled:

```dotenv
INTERRUPTION_MIN_DURATION=0.8
INTERRUPTION_MIN_WORDS=1
FALSE_INTERRUPTION_TIMEOUT=1.5
RESUME_FALSE_INTERRUPTION=true
```

If coughs still interrupt playback, raise `INTERRUPTION_MIN_DURATION` gradually
to `1.0` or `1.2`. Raising `INTERRUPTION_MIN_WORDS` to `2` is stricter, but then
a one-word command such as "stop" will no longer interrupt immediately.

## 4. Open only the required LAN ports

Permit these paths from trusted LAN clients:

- TCP 80 and 443: Caddy HTTP/HTTPS
- TCP 7881: LiveKit WebRTC TCP fallback
- UDP 50000-50100: LiveKit WebRTC media

Do not expose Redis, Qwen, Chatterbox, the token API, or container-internal port
7880. They remain on the private Compose network. Be aware that Docker-published
ports interact with host firewall rules; enforce restrictions in the
`DOCKER-USER` chain or the upstream network firewall.

## 5. Validate and start the GPU stack

Resolve the merged configuration before starting it:

```bash
sudo docker compose \
  --env-file .env \
  --env-file .env.gpu \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  config --quiet
```

Pull/build and start:

```bash
sudo docker compose \
  --env-file .env \
  --env-file .env.gpu \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  up -d --build
```

Keep at least 50 GB of free Docker storage. The first run pulls a large Qwen
image, builds the Chatterbox API image, and
downloads both model weight sets. `whisper-model-setup` remains as a compatibility
one-shot and should finish as `Exited (0)` after logging that setup was skipped;
that is success, not a crashed service. Watch startup with:

```bash
sudo docker compose \
  --env-file .env \
  --env-file .env.gpu \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  ps -a

sudo docker compose \
  --env-file .env \
  --env-file .env.gpu \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  logs -f whisper-model-setup faster-whisper kokoro voice-core
```

Verify both inference containers see the T4 and inspect memory allocation:

```bash
sudo docker compose exec faster-whisper nvidia-smi
sudo docker compose exec kokoro nvidia-smi
```

The Qwen service keeps the legacy Compose name `faster-whisper`, and the
Chatterbox service keeps the name `kokoro`. This is intentional: it preserves
the base stack dependency graph and makes rollback non-destructive.

If Chatterbox reports CUDA out-of-memory, lower
`QWEN_GPU_MEMORY_UTILIZATION` in `.env.gpu` from `0.52` to `0.48`, recreate both
inference services, and test again. Do not raise it above `0.55` on a single T4.

If the machine has multiple GPUs, replace `count: 1` in
`docker-compose.gpu.yml` with `device_ids: ['0']` for each GPU-enabled service.
Do not specify both `count` and `device_ids`.

## 6. Trust local TLS and test

Export the new host's Caddy root CA:

```bash
sudo docker compose cp \
  caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
```

Install that certificate as a trusted root on each browser device. Then verify:

```bash
curl --fail --cacert ./caddy-root.crt \
  "https://${VOICE_HOST}/api/health"
```

The response should report `deployment_mode: gpu`, model
`Qwen/Qwen3-ASR-1.7B`, STT device `cuda`, compute type `float16`, TTS model
`chatterbox-multilingual-v3`, and healthy STT/TTS dependencies. Open
`https://<VOICE_HOST>`, connect the microphone, and test English, Mandarin,
Malay, mixed utterances, interruption, and then a second browser session.

## 7. Persistence, backup, and rollback

The minimum backup set is:

- `.env` and `.env.gpu`, stored securely outside Git
- `caddy-data` and `caddy-config`, if clients should keep trusting the same CA
- `redis-data` only if short-lived coordination state matters
- `whisper-models` optionally; GPU mode reuses it as the Qwen Hugging Face cache
- `chatterbox-models` optionally; it is a downloadable Chatterbox cache

A fresh host creates a new Caddy CA. If the old `caddy-data` volume is not
migrated, install the new root certificate on clients and remove trust for the
old one when it is no longer used.

To roll back to CPU mode without changing application data:

```bash
sudo docker compose \
  --env-file .env \
  --env-file .env.cpu \
  -f docker-compose.yml \
  -f docker-compose.cpu.yml \
  up -d --build
```

Keep the same Compose project name and working directory when switching modes
so Docker reuses the named volumes. Back up the Caddy volumes before destructive
host maintenance or Docker storage migration.
