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

Confirm a container can use the GPU. This must succeed before deploying the
application:

```bash
sudo docker run --rm --gpus all \
  nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi
```

Docker's Compose GPU syntax requires `capabilities: [gpu]`; the supplied GPU
override already includes it for both Whisper and Kokoro.

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

The supplied `.env.gpu` selects CUDA/float16 and the multilingual large-v3
turbo Whisper model. To favor VRAM efficiency over accuracy, change its
`STT_MODEL` to `Systran/faster-whisper-small` and its compute type to `int8`.

## 4. Open only the required LAN ports

Permit these paths from trusted LAN clients:

- TCP 80 and 443: Caddy HTTP/HTTPS
- TCP 7881: LiveKit WebRTC TCP fallback
- UDP 50000-50100: LiveKit WebRTC media

Do not expose Redis, Whisper, Kokoro, the token API, or container-internal port
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

The first run downloads the Whisper model. `whisper-model-setup` should finish
as `Exited (0)`; that is success, not a crashed service. Watch startup with:

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

Verify both inference containers see the GPU:

```bash
sudo docker compose exec faster-whisper nvidia-smi
sudo docker compose exec kokoro nvidia-smi
```

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

The response should report `deployment_mode: gpu`, STT device `cuda`, compute
type `float16`, and healthy STT/TTS dependencies. Open
`https://<VOICE_HOST>`, connect the microphone, and test English, Mandarin,
interruption, and a second simultaneous browser session.

## 7. Persistence, backup, and rollback

The minimum backup set is:

- `.env` and `.env.gpu`, stored securely outside Git
- `caddy-data` and `caddy-config`, if clients should keep trusting the same CA
- `redis-data` only if short-lived coordination state matters
- `whisper-models` optionally; it is a downloadable cache

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
