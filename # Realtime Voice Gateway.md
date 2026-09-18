# Realtime Voice Gateway

## 1. Project Goal

Build a **self-hosted realtime voice assistant gateway** that behaves similarly to **ChatGPT Voice / Gemini Live**, using Docker Compose on a Linux server.

The system must support:

* realtime microphone input
* streaming speech-to-text
* streaming LLM response
* streaming text-to-speech
* low conversational latency
* natural turn detection
* user interruption / barge-in while AI is speaking
* immediate cancellation of current AI speech
* cancellation of active LLM generation when interrupted
* Docker Compose deployment
* GPU mode
* CPU-only mode
* initial direct connection to an OpenAI-compatible LLM API
* later replacement of the direct LLM backend with OpenClaw
* minimal custom glue code only where necessary

The initial project scope should remain focused.

Do **not** add unnecessary features such as RAG, multiple agent frameworks, multiple TTS engines, Kubernetes, or advanced persistence until the core realtime pipeline works reliably.

---

# 2. Development Objectives

There are only two main objectives.

## Objective 1 — Direct OpenAI-Compatible LLM

Build a complete working realtime voice pipeline using:

```text
LiveKit
+
Silero VAD
+
LiveKit Turn Detector
+
faster-whisper
+
OpenAI-compatible LLM API
+
Kokoro
```

The entire stack should run through Docker Compose except for the LLM, which may initially be an external API endpoint.

The LLM should be configured using:

```env
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
```

The first milestone is:

> Run Docker Compose, open the web interface, speak naturally to the assistant, receive a streamed spoken response through Kokoro, and interrupt the AI while it is speaking.

---

## Objective 2 — Replace Direct LLM with OpenClaw

Only after Objective 1 works reliably, replace the direct OpenAI-compatible LLM backend with OpenClaw.

Before:

```text
Voice Core
    │
    ▼
OpenAI-Compatible LLM
```

After:

```text
Voice Core
    │
    ▼
OpenClaw Adapter
    │
    ▼
OpenClaw Gateway
    │
    ▼
OpenClaw Agent
```

Everything else must remain unchanged:

```text
LiveKit
Silero
Turn Detector
faster-whisper
Kokoro
Frontend
Streaming
Barge-in
GPU/CPU deployment
```

The user should not notice whether the backend is:

```text
Direct OpenAI-compatible LLM
```

or:

```text
OpenClaw
```

The voice experience should remain the same.

---

# 3. Core Architecture

## Objective 1

```text
Browser / App
Mic + Speaker
      │
      │ WebRTC
      ▼
┌──────────────┐
│   LiveKit    │
│    Server    │
└──────┬───────┘
       │
       ▼
┌──────────────────────┐
│ Realtime Voice Core  │
│                      │
│ Silero VAD           │
│ Turn Detector        │
│ Session Handling     │
│ Streaming Pipeline   │
│ Interruption Logic   │
└─────────┬────────────┘
          │
          ├─────────────────────┐
          │                     │
          ▼                     ▼
  faster-whisper        OpenAI-Compatible
       STT                    LLM API
                                  │
                                  ▼
                             Text Stream
                                  │
                                  ▼
                               Kokoro
                                  │
                             PCM Stream
                                  │
                                  ▼
                               LiveKit
                                  │
                                  ▼
                                User
```

---

# 4. Realtime Conversation Flow

The full flow should be:

```text
1. User opens the browser interface.

2. Browser connects to LiveKit.

3. User allows microphone access.

4. Browser publishes microphone audio.

5. LiveKit sends audio to the Voice Core.

6. Silero VAD detects speech start.

7. faster-whisper performs speech recognition.

8. LiveKit Turn Detector determines when the user has finished the turn.

9. Final transcript is sent to the configured OpenAI-compatible LLM.

10. LLM response streams token-by-token.

11. Voice Core groups the stream into natural speakable phrases.

12. Kokoro begins TTS before the full LLM response is complete.

13. Kokoro returns streaming PCM audio.

14. Voice Core publishes audio through LiveKit.

15. User hears the AI response.

16. If the user interrupts, current generation and playback are cancelled immediately.
```

---

# 5. Mandatory Barge-In Behavior

Barge-in is one of the most important requirements.

Example:

```text
AI:
"You should first verify the host configuration and then—"

User:
"Wait, what about the storage?"

AI stops immediately.
```

Required behavior:

```text
AI speaking
     │
     ▼
User begins speaking
     │
     ▼
Silero detects speech
     │
     ├── stop current LiveKit audio output
     ├── clear queued audio
     ├── cancel Kokoro generation
     ├── cancel current LLM stream
     └── start listening to user
     │
     ▼
faster-whisper transcribes the new request
     │
     ▼
new request is sent to the backend
```

Do not only mute audio.

The active TTS and LLM operations must also be cancelled.

This avoids wasting resources and ensures the conversation state remains correct.

---

# 6. LiveKit

Use:

```text
LiveKit Server
+
LiveKit Agents SDK
```

Responsibilities:

* WebRTC
* room management
* microphone transport
* realtime audio publishing
* browser connectivity
* agent connectivity
* media transport
* interruption-related session control

LiveKit is the realtime media layer.

---

# 7. Silero VAD

Use:

```text
Silero VAD
```

Responsibilities:

* detect user speech start
* detect user speech stop
* trigger fast barge-in
* reduce delay before interruption

Example:

```text
AI speaking
    │
User starts talking
    │
Silero detects speech
    │
Stop AI immediately
```

---

# 8. LiveKit Turn Detector

Use:

```text
LiveKit Turn Detector v1-mini
```

Purpose:

Determine whether the user has actually completed their turn.

Silero only knows:

```text
speech
silence
speech
```

The turn detector should help distinguish:

```text
"I'm not sure..."
```

from:

```text
"I am finished speaking."
```

Use both:

```text
Silero VAD
+
LiveKit Turn Detector
```

Silero handles fast interruption.

The Turn Detector handles natural end-of-turn detection.

---

# 9. Speech-to-Text

Use:

```text
faster-whisper
```

Prefer a server implementation that supports streaming or low-latency transcription.

Starting model candidate:

```text
large-v3-turbo (multilingual; validate against large-v3 if needed)
```

Recognize Malaysian-style mixed Mandarin Chinese, Malay, and English, including language switches within one utterance. Preserve the spoken languages in the transcript rather than translating everything into English. English-only Distil-Whisper models are not suitable for this requirement. Model selection remains subject to mixed-language accuracy and VM resource testing.

The Voice Core should communicate with STT through an internal API.

Example:

```env
STT_BASE_URL=http://faster-whisper:8000
```

The application should not care whether faster-whisper runs on GPU or CPU.

---

# 10. LLM Backend — Objective 1

The Voice Core should initially connect directly to an OpenAI-compatible API.

Configuration:

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=xxxxxxxx
LLM_MODEL=example-model
```

Possible compatible backends include:

```text
OpenAI
vLLM
llama.cpp
SGLang
Ollama-compatible API
New API
CLIProxyAPI
other OpenAI-compatible providers
```

The initial provider is OpenAI using a server-side API key. Select an available streaming text model through `LLM_MODEL`; do not hardcode a model or expose its API key to the browser. Other OpenAI-compatible providers are later compatibility targets.

The LLM must use streaming.

Do not use:

```text
user speaks
↓
wait for complete LLM answer
↓
send full text to TTS
```

Use:

```text
user speaks
↓
streaming LLM
↓
phrase chunker
↓
streaming TTS
↓
audio immediately
```

---

# 11. Agent Backend Abstraction

Even though Objective 1 uses a direct LLM API, the implementation should keep the backend behind a small interface so OpenClaw can replace it later.

Conceptual interface:

```python
class AgentBackend:

    async def create_session(self, session_id):
        ...

    async def send_message(
        self,
        session_id: str,
        text: str
    ):
        """Yield streaming text chunks."""
        ...

    async def cancel(self, session_id: str):
        ...

    async def close_session(self, session_id: str):
        ...
```

Objective 1:

```text
AgentBackend
     │
     ▼
OpenAICompatibleBackend
```

Objective 2:

```text
AgentBackend
     │
     ▼
OpenClawBackend
```

Do not implement other agent frameworks now.

---

# 12. Kokoro TTS

Kokoro should be the only TTS backend required for Objective 1.

Initial spoken replies are English or Mandarin Chinese. Understanding Malay and mixed-language input is required, but Malay speech synthesis and a specifically Malaysian voice/accent are not required for this milestone. Use a supported voice for the chosen reply language and validate both languages. By default, follow the user’s explicit reply-language preference; otherwise use the dominant English/Mandarin context, with English as the fallback. Do not assume one Kokoro voice naturally handles arbitrary language switching within a sentence.

Responsibilities:

* low-latency speech synthesis
* streaming output
* conversational speech

Prefer PCM output.

Desired internal flow:

```text
Kokoro
   │
   ▼
PCM
   │
   ▼
LiveKit
   │
   ▼
WebRTC / Opus
```

Avoid unnecessary:

```text
TTS
↓
MP3
↓
decode MP3
↓
PCM
↓
Opus
```

where possible.

Use an internal endpoint such as:

```env
TTS_BASE_URL=http://kokoro:8880
```

The Voice Core should not care whether Kokoro uses GPU or CPU.

---

# 13. Phrase Chunking

Do not send one token at a time to TTS.

The Voice Core should buffer the LLM stream into short natural phrases.

Example LLM output:

```text
"Sure. First check the host connection.
Then verify the storage status."
```

TTS should start with:

```text
"Sure. First check the host connection."
```

while the LLM continues generating:

```text
"Then verify the storage status."
```

Phrase splitting should consider:

```text
.
,
?
!
;
:
```

and minimum/maximum text lengths to avoid very small or excessively long chunks.

---

# 14. Frontend

Create a minimal web frontend.

Recommended:

```text
React
or
Next.js
+
LiveKit JS SDK
```

Initial UI should support:

* Connect
* Disconnect
* Microphone permission
* Listening state
* Thinking state
* Speaking state
* User transcript
* AI transcript
* Basic audio waveform or level indicator

Do not spend time on advanced UI during Objective 1.

---

# 15. LiveKit Authentication

Never expose the LiveKit API secret to the browser.

Implement a backend endpoint such as:

```http
POST /api/token
```

Flow:

```text
Browser
   │
   ▼
Voice Core token API
   │
   ▼
Generate short-lived LiveKit JWT
   │
   ▼
Browser connects to LiveKit
```

The token endpoint may be implemented using FastAPI inside the Voice Core container.

---

# 16. Docker Compose Requirement

The system will initially run on a Linux virtual machine with 16 GB RAM and an NVIDIA T4 or higher GPU passed through to the VM. Initially deploy on the LAN only. Support two concurrent users in separate, isolated conversations. Exact vCPU count, Linux distribution, available disk space, and actual GPU/VRAM allocation must be recorded before deployment and benchmarking.

The Compose deployment should initially contain:

```text
redis
livekit
voice-core
faster-whisper
kokoro
frontend
caddy
```

The LLM does not need to run locally during Objective 1.

Architecture:

```text
Linux Docker Host

├── Caddy
├── Redis
├── LiveKit
├── Voice Core
├── faster-whisper
├── Kokoro
└── Frontend

          │
          │ HTTPS
          ▼

External OpenAI-Compatible LLM API
```

---

# 17. GPU and CPU Deployment Requirement

The same repository must support both:

```text
GPU mode
```

and:

```text
CPU-only mode
```

without changing application source code.

Primary production target:

```text
Linux
+
Docker Engine
+
Docker Compose
+
NVIDIA GPU
+
NVIDIA Container Toolkit
```

CPU mode should exist as a fallback and testing option.

---

# 18. Recommended Compose Layout

Use:

```text
docker-compose.yml
docker-compose.gpu.yml
docker-compose.cpu.yml
```

The base file should contain common services.

Example:

```text
docker-compose.yml

├── redis
├── livekit
├── voice-core
├── frontend
├── caddy
├── faster-whisper
└── kokoro
```

The override files change device/runtime configuration.

---

# 19. GPU Mode

Run using something like:

```bash
docker compose \
  --env-file .env.gpu \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  up -d
```

Recommended GPU allocation:

```text
GPU
├── faster-whisper
└── Kokoro if GPU inference is useful/supported

CPU
├── LiveKit
├── Redis
├── Caddy
├── Voice Core
├── Silero
└── Turn Detector
```

The external LLM does not consume local GPU resources in Objective 1.

---

# 20. CPU Mode

Run using:

```bash
docker compose \
  --env-file .env.cpu \
  -f docker-compose.yml \
  -f docker-compose.cpu.yml \
  up -d
```

CPU mode should use CPU-efficient inference settings.

Example:

```env
STT_DEVICE=cpu
STT_COMPUTE_TYPE=int8
```

GPU mode:

```env
STT_DEVICE=cuda
STT_COMPUTE_TYPE=float16
```

The exact compute mode should follow what the selected inference server supports.

---

# 21. Application Must Be Device-Agnostic

The Voice Core should never contain logic such as:

```python
if gpu:
    connect_to_gpu_whisper()
else:
    connect_to_cpu_whisper()
```

Instead, both environments should expose the same service endpoint:

```text
http://faster-whisper:8000
```

and:

```text
http://kokoro:8880
```

The container implementation changes, not the Voice Core.

This is an important architectural requirement.

---

# 22. NVIDIA Requirements

GPU deployment documentation should include:

```text
NVIDIA driver
Docker Engine
NVIDIA Container Toolkit
```

GPU validation example:

```bash
docker run --rm --gpus all \
  nvidia/cuda:<compatible-version> \
  nvidia-smi
```

GPU deployment should only proceed after this succeeds.

---

# 23. GPU Override Concept

Conceptual example:

```yaml
services:

  faster-whisper:
    environment:
      STT_DEVICE: cuda
      STT_COMPUTE_TYPE: float16

    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities:
                - gpu


  kokoro:
    environment:
      TTS_DEVICE: cuda

    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities:
                - gpu
```

Exact image names and environment variables must be verified during implementation.

Do not blindly assume upstream parameter names.

---

# 24. CPU Override Concept

```yaml
services:

  faster-whisper:
    environment:
      STT_DEVICE: cpu
      STT_COMPUTE_TYPE: int8


  kokoro:
    environment:
      TTS_DEVICE: cpu
```

Again, exact settings should match the selected upstream images.

---

# 25. Environment Files

Recommended:

```text
.env.example
.env.gpu.example
.env.cpu.example
```

Common configuration example:

```env
# LiveKit

LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=

# LLM

LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=

# STT

STT_BASE_URL=http://faster-whisper:8000
STT_MODEL=large-v3-turbo

# TTS

TTS_BASE_URL=http://kokoro:8880
TTS_VOICE=

# Deployment

DEPLOYMENT_MODE=gpu
```

GPU example:

```env
DEPLOYMENT_MODE=gpu
STT_DEVICE=cuda
STT_COMPUTE_TYPE=float16
```

CPU example:

```env
DEPLOYMENT_MODE=cpu
STT_DEVICE=cpu
STT_COMPUTE_TYPE=int8
```

---

# 26. Internal Docker Networking

Use an internal network such as:

```text
voice-net
```

Internal-only services:

```text
Redis
faster-whisper
Kokoro
Voice Core internal API
```

These should not be directly exposed to the internet.

For the initial LAN deployment, expose only the required client-facing services to the LAN; public internet ingress is not required. Outbound access is still needed for the OpenAI API and initial dependency/model downloads.

Client-facing services should be limited to what is required for:

```text
HTTPS
WebRTC
LiveKit signaling
ICE/TURN
```

---

# 27. Reverse Proxy

Use:

```text
Caddy
```

for:

* HTTPS
* frontend
* API endpoint
* token API
* WebSocket proxying where appropriate

For access from other LAN devices, serve the frontend and signaling over trusted HTTPS/WSS. Use a LAN-resolvable hostname and a certificate trusted by client devices; if using Caddy’s internal CA, document client trust installation. A plain HTTP LAN IP is not the browser microphone deployment path.

LiveKit must advertise an IP reachable from LAN clients. Configure VM networking and firewall rules accordingly; verify connectivity from a separate LAN device. Public TURN infrastructure is deferred unless LAN testing demonstrates a relay requirement.

LiveKit media ports still need correct direct exposure for WebRTC.

Do not try to tunnel all WebRTC UDP traffic through a normal HTTP reverse proxy.

---

# 28. Suggested Repository Structure

```text
realtime-voice/
│
├── docker-compose.yml
├── docker-compose.gpu.yml
├── docker-compose.cpu.yml
│
├── .env.example
├── .env.gpu.example
├── .env.cpu.example
│
├── README.md
│
├── livekit/
│   └── livekit.yaml
│
├── caddy/
│   └── Caddyfile
│
├── voice-core/
│   ├── Dockerfile
│   ├── requirements.txt
│   │
│   ├── main.py
│   ├── api.py
│   ├── config.py
│   ├── session.py
│   │
│   ├── stt/
│   │   └── faster_whisper.py
│   │
│   ├── agents/
│   │   ├── base.py
│   │   └── openai_compatible.py
│   │
│   └── tts/
│       └── kokoro.py
│
└── frontend/
    ├── Dockerfile
    ├── package.json
    └── src/
```

After Objective 1 works:

```text
voice-core/agents/openclaw.py
```

can be added.

---

# 29. Voice Core Responsibilities

The Voice Core is the main custom software.

Responsibilities:

```text
LiveKit agent lifecycle
LiveKit room/session integration
Silero VAD
Turn Detector
STT communication
LLM communication
LLM streaming
phrase chunking
TTS communication
PCM streaming
conversation history
barge-in
cancellation
token API
health checks
logging
```

Do not modify upstream LiveKit, Whisper, or Kokoro unless absolutely necessary.

The custom code should mainly be the orchestration layer.

---

# 30. Conversation History

Objective 1 should maintain basic in-memory conversation history for each active session.

Example:

```text
system
user
assistant
user
assistant
```

No database is required initially.

Each connected user has a separate room/session and isolated history, generation, playback, and cancellation state. Interrupting one user’s response must not affect another user.

When interrupted, retain only the assistant text corresponding to audio actually played, using LiveKit playback tracking where supported. Do not store unspoken generated text as if the user heard it.

History may be lost when the Voice Core restarts.

Persistent chat storage is out of scope for now.

---

# 31. Session Cancellation

Every active response should have cancellable tasks.

Conceptually:

```text
Session
├── current LLM task
├── current TTS task
└── current audio playback
```

When barge-in occurs:

```text
cancel current LLM task
cancel current TTS task
flush outgoing audio
begin new input turn
```

Cancellation must be designed from the start instead of added later.

---

# 32. Health Monitoring

Expose:

```http
GET /health
```

Example GPU result:

```json
{
  "livekit": "ok",
  "stt": {
    "status": "ok",
    "device": "cuda",
    "compute_type": "float16"
  },
  "llm": {
    "status": "ok",
    "backend": "openai_compatible"
  },
  "tts": {
    "status": "ok",
    "device": "cuda"
  }
}
```

CPU example:

```json
{
  "livekit": "ok",
  "stt": {
    "status": "ok",
    "device": "cpu",
    "compute_type": "int8"
  },
  "llm": {
    "status": "ok",
    "backend": "openai_compatible"
  },
  "tts": {
    "status": "ok",
    "device": "cpu"
  }
}
```

Do not silently fall back to CPU without exposing that information.

---

# 33. Logging and Metrics

At minimum log:

```text
session ID
speech start
speech end
STT result
STT latency
turn detection latency
LLM time-to-first-token
TTS time-to-first-audio
barge-in event
cancellation
overall response latency
backend errors
```

Example:

```text
session=abc123
stt_final=420ms
turn_detection=210ms
llm_ttft=260ms
tts_first_audio=310ms
total_response=980ms
```

This will be important for performance tuning.

---

# 34. Performance Target

Desired end-user flow:

```text
User finishes speaking
        │
        ▼
Turn detection
        │
        ▼
LLM starts streaming
        │
        ▼
Kokoro starts generating
        │
        ▼
AI begins speaking
```

Target approximately:

```text
0.6–1.5 seconds
```

where hardware, network latency, and selected models allow.

GPU mode should prioritize latency.

CPU mode only needs to remain usable and functionally equivalent, including two isolated sessions. Measure CPU latency separately; do not claim the GPU latency target applies to CPU mode.

Benchmark both one and two simultaneously active users with warmed models. Measure from actual end of user speech to first audible response, report p50/p95, and record VM CPU/RAM, GPU/VRAM, model versions, and network conditions. The 0.6–1.5 second range is an optimization target, not a guaranteed result on untested hardware. Record interruption latency from user speech onset to last audible assistant audio; an initial engineering target is p95 at or below 500 ms, subject to validation.

---

# 35. Objective 1 Success Criteria

Objective 1 is complete only when:

```text
✓ docker compose starts successfully

✓ both GPU and CPU deployment modes exist

✓ browser can connect to LiveKit

✓ microphone works

✓ user audio reaches the Voice Core

✓ Silero detects speech

✓ faster-whisper transcribes speech

✓ Turn Detector correctly finishes the turn

✓ transcript reaches the OpenAI-compatible LLM

✓ LLM response streams

✓ Kokoro starts speaking before full LLM completion

✓ PCM audio streams back through LiveKit

✓ multi-turn conversation works

✓ Malaysian-style mixed Mandarin/Malay/English input is transcribed and understood

✓ English and Mandarin spoken replies work with supported Kokoro voices

✓ two simultaneous users have isolated conversations and cancellation

✓ a second LAN device connects using trusted HTTPS/WSS

✓ user can interrupt while AI is speaking

✓ interruption stops audio immediately

✓ active Kokoro generation is cancelled

✓ active LLM stream is cancelled

✓ new user turn starts correctly

✓ /health shows actual CPU/GPU mode

✓ Docker Compose restart does not require source-code changes
```

---

# 36. Objective 2 — OpenClaw

Only after Objective 1 is stable, add:

```text
voice-core/agents/openclaw.py
```

Architecture:

```text
faster-whisper
      │
      ▼
Voice Core
      │
      ▼
OpenClaw Backend
      │
      ▼
OpenClaw Gateway
      │
      ▼
OpenClaw Agent
      │
      ▼
Kokoro
```

OpenClaw will provide:

```text
agent logic
tools
skills
memory
model routing
session logic
```

The Voice Core will continue to provide:

```text
LiveKit
STT
VAD
turn detection
streaming
TTS
barge-in
audio handling
```

---

# 37. OpenClaw Barge-In Requirement

When OpenClaw is used:

```text
User interrupts
      │
      ├── stop LiveKit audio
      ├── clear TTS queue
      ├── cancel Kokoro
      └── cancel / steer OpenClaw generation
```

Then:

```text
new user speech
      ↓
Whisper
      ↓
same OpenClaw conversation/session
```

The user experience should remain identical to Objective 1.

---

# 38. Explicitly Out of Scope

Ignore these for now:

```text
VoxCPM
VibeVoice
voice cloning
LangGraph
CrewAI
AutoGen
multiple agent frameworks
multiple TTS backends
multiple STT backends
RAG
vector database
PostgreSQL
persistent memory
Kubernetes
mobile applications
advanced authentication
multi-agent routing
complex UI
podcast generation
long-form narration
```

Do not implement these until Objectives 1 and 2 are complete.

---

# 39. Development Principles

1. Docker Compose first.
2. Linux is the primary host OS.
3. GPU and CPU modes must both work.
4. GPU/CPU selection must not require source changes.
5. Use separate containers for major services.
6. Keep the Voice Core thin.
7. Stream every stage.
8. Design cancellation from the beginning.
9. Use Silero for rapid speech-start detection.
10. Use the Turn Detector for natural end-of-turn decisions.
11. Prefer PCM internally.
12. Keep the LLM behind a minimal backend abstraction.
13. Implement direct OpenAI-compatible LLM first.
14. Add OpenClaw only after the direct pipeline works.
15. Do not over-engineer the first release.
16. Pin container and Python package versions.
17. Do not use `latest` for production deployment.
18. Internal inference services should not be publicly exposed.
19. Health checks must show whether inference is using GPU or CPU.
20. Functionality should remain identical between CPU and GPU modes; only performance may differ.

---

# 40. Final Stage 1 Architecture

```text
                         Linux Server

┌───────────────────────────────────────────────────┐
│                                                   │
│ Caddy                                             │
│   │                                               │
│   ▼                                               │
│ Frontend ───────────────▶ LiveKit                 │
│                              │                    │
│                              ▼                    │
│                        Voice Core                 │
│                              │                    │
│                    ┌─────────┴─────────┐          │
│                    │                   │          │
│                    ▼                   ▼          │
│             faster-whisper       External LLM    │
│                    │                   │          │
│                    └─────────┬─────────┘          │
│                              ▼                    │
│                           Kokoro                  │
│                              │                    │
│                              ▼                    │
│                           LiveKit                 │
│                              │                    │
│                              ▼                    │
│                            Browser                │
│                                                   │
│ Redis                                             │
│                                                   │
└───────────────────────────────────────────────────┘
```

---

# 41. Final Stage 2 Architecture

```text
                         Linux Server

┌───────────────────────────────────────────────────┐
│                                                   │
│ Browser                                           │
│    │                                              │
│    ▼                                              │
│ LiveKit                                           │
│    │                                              │
│    ▼                                              │
│ Voice Core                                        │
│    │                                              │
│    ├── Silero                                     │
│    ├── Turn Detector                              │
│    ├── faster-whisper                             │
│    │                                              │
│    ▼                                              │
│ OpenClaw Adapter                                  │
│    │                                              │
│    ▼                                              │
│ OpenClaw Gateway / Agent                          │
│    │                                              │
│    ▼                                              │
│ Kokoro                                            │
│    │                                              │
│    ▼                                              │
│ LiveKit                                           │
│    │                                              │
│    ▼                                              │
│ Browser                                           │
│                                                   │
└───────────────────────────────────────────────────┘
```

---

# 42. Instruction for the Development Session

Start with **Objective 1 only**.

Generate a complete working repository containing:

```text
docker-compose.yml
docker-compose.gpu.yml
docker-compose.cpu.yml

.env.example
.env.gpu.example
.env.cpu.example

README.md

livekit/livekit.yaml

caddy/Caddyfile

voice-core/Dockerfile
voice-core/requirements.txt
voice-core/main.py
voice-core/api.py
voice-core/config.py
voice-core/session.py

voice-core/agents/base.py
voice-core/agents/openai_compatible.py

voice-core/stt/faster_whisper.py

voice-core/tts/kokoro.py

frontend/
```

Requirements for the first implementation:

```text
LiveKit
Silero VAD
LiveKit Turn Detector v1-mini
faster-whisper
OpenAI-compatible external LLM
Kokoro
minimal browser frontend
GPU deployment mode
CPU deployment mode
streaming response
barge-in
LLM cancellation
TTS cancellation
health endpoint
```

The LLM must be configurable using:

```env
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
```

Do not implement OpenClaw yet.

However, the LLM interaction must be behind the `AgentBackend` abstraction so the direct backend can later be replaced with an OpenClaw adapter.

The first milestone is:

> **On a Linux server, run the stack through Docker Compose in either GPU or CPU mode, open the browser, talk naturally with an OpenAI-compatible LLM, hear streaming Kokoro speech, and interrupt the AI naturally while it is speaking.**

Only after this works reliably should development move to:

> **Objective 2 — replace the direct OpenAI-compatible backend with OpenClaw without changing the realtime voice pipeline.**


---

# 43. Confirmed Scope and Implementation Readiness

The following decisions were confirmed by the user and take precedence over earlier illustrative examples:

* Input: Malaysian-style mixed Chinese, Malay, and English. Interpret Chinese as Mandarin for the initial milestone; other Chinese dialects are not yet specified.
* Output: start with English and Mandarin Chinese spoken replies using Kokoro. Malay spoken output is deferred.
* Host: Linux VM, 16 GB system RAM, NVIDIA T4 or higher through GPU passthrough. Verify the GPU is available inside the VM and containers.
* Network: LAN first, with outbound OpenAI API access. No public deployment requirement for this milestone.
* Capacity: two concurrent users, one user and one assistant per independent room/session. Shared group conversations are out of scope.
* LLM: OpenAI API key first, with model configurable through the existing backend abstraction.
* Access control: user authentication and token-endpoint access controls are deferred for this LAN milestone. Keep secrets server-side, generate scoped room tokens, and keep inference services internal. This does not remove session isolation requirements.
* Objective 1 only: do not implement OpenClaw yet.

## Implementation checks, not additional product decisions

Resolve these through a small integration prototype before declaring the complete pipeline validated:

1. **Streaming STT:** select and pin an actual faster-whisper server that accepts incremental audio and exposes partial/final transcript semantics. Partial text may change; commit only the final user turn to the LLM. A whole-utterance upload alone does not satisfy the streaming STT requirement.
2. **Turn detection:** explicitly select local `v1-mini` with a compatible pinned LiveKit Agents SDK and Silero configuration. Current documented language support includes English and Chinese, but not Malay. Test Malay and mixed-language turns, and implement a bounded VAD/silence timeout fallback when needed. Do not substitute Indonesian for Malay or claim semantic Malay support without evidence.
3. **Session ownership:** prefer LiveKit AgentSession orchestration for audio, turn handling, playback, and interruption. Keep custom adapters thin and avoid a competing custom session state machine. Define one authoritative owner for conversation history across the LiveKit session and AgentBackend.
4. **Cancellation:** distinguish local task cancellation, transport closure, and server-side inference cancellation. Verify the chosen Kokoro server and LLM API behavior. Drop stale chunks using response IDs, flush queues, and ensure cancelled output never enters a later response. If server-side compute cancellation cannot be guaranteed, document the limitation and resolve the original hard-cancellation requirement before declaring it passed; closing a stream alone is not proof.
5. **Audio and buffering:** define PCM sample format/rate/channels at each adapter, resampling ownership, bounded queues, and backpressure. Support English and Chinese punctuation in phrase chunking, with a maximum waiting time for streams without punctuation.
6. **Lifecycle and errors:** configure session idle limits, bounded in-memory history/context, dependency timeouts, and disconnect cleanup. Default explicit disconnect to ending the session; a fresh connection starts a fresh conversation. Show backend failures in the UI and avoid replaying already-spoken text after retries.
7. **False interruptions and echo:** configure explicit interruption thresholds and recovery behavior; test with speakers and headphones. Do not assume background noise suppression or browser echo cancellation eliminates all false triggers.
8. **Model readiness:** cache model downloads in persistent volumes, warm models before reporting ready, pin images/packages/model revisions, and distinguish process liveness from inference readiness. Report actual inference device without silent fallback. Health checks must not continuously generate billable LLM requests.
9. **Logging defaults:** log timings, session/response IDs, errors, and transcript availability. Raw audio recording is disabled; transcript content logging is opt-in for debugging rather than enabled by default. This refines the earlier “STT result” logging example.
10. **Acceptance:** test both languages of spoken output, mixed-language input, two overlapping conversations, barge-in during generation/playback, repeated interruptions, stale-output rejection, dependency failure, and CPU/GPU modes. Record actual results; configuration files alone are not evidence that a mode works.

## Deployment values to collect later

These do not block repository development: Linux distribution, vCPU allocation, available model-cache storage, actual GPU/VRAM, LAN hostname/IP and certificate trust setup, OpenAI model identifier, and server-side API key provisioning. Confirm them before deployment and performance acceptance.

## References checked during requirements review

* Kokoro voice/language inventory: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
* Faster-whisper model and inference documentation: https://github.com/SYSTRAN/faster-whisper
* Faster-whisper supported model identifiers: https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/utils.py
* LiveKit local turn detector and supported languages: https://docs.livekit.io/agents/logic/turns/turn-detector/
* LiveKit session turn and interruption handling: https://docs.livekit.io/agents/logic/turns/
