import { Room, RoomEvent, Track, type RemoteTrack } from "livekit-client";
import "./styles.css";

type TokenResponse = {
  token: string;
  url: string;
  room: string;
  identity: string;
};

const connectButton = document.querySelector<HTMLButtonElement>("#connect")!;
const disconnectButton = document.querySelector<HTMLButtonElement>("#disconnect")!;
const displayName = document.querySelector<HTMLInputElement>("#display-name")!;
const statusLabel = document.querySelector<HTMLSpanElement>("#status")!;
const statusDot = document.querySelector<HTMLSpanElement>("#status-dot")!;
const transcript = document.querySelector<HTMLDivElement>("#transcript")!;
const roomName = document.querySelector<HTMLSpanElement>("#room-name")!;
const errorLabel = document.querySelector<HTMLParagraphElement>("#error")!;
const levelBar = document.querySelector<HTMLSpanElement>("#level-bar")!;
const remoteAudio = document.querySelector<HTMLAudioElement>("#remote-audio")!;

let room: Room | undefined;
let meterTimer: number | undefined;
const transcriptLines = new Map<string, HTMLParagraphElement>();

function setStatus(value: string, active = false): void {
  statusLabel.textContent = value;
  statusDot.classList.toggle("active", active);
}

function showError(error: unknown): void {
  errorLabel.textContent = error instanceof Error ? error.message : String(error);
}

function appendTranscript(id: string, text: string, speaker: string, final: boolean): void {
  transcript.querySelector(".empty")?.remove();
  let line = transcriptLines.get(id);
  if (!line) {
    line = document.createElement("p");
    line.className = `utterance ${speaker}`;
    transcriptLines.set(id, line);
    transcript.append(line);
  }
  line.textContent = text;
  line.classList.toggle("interim", !final);
  transcript.scrollTop = transcript.scrollHeight;
}

function attachAudio(track: RemoteTrack): void {
  track.attach(remoteAudio);
  void remoteAudio.play().catch(() => {
    showError("Audio playback was blocked. Click Connect again to permit playback.");
  });
}

function startLevelMeter(activeRoom: Room): void {
  meterTimer = window.setInterval(() => {
    const level = activeRoom.localParticipant.audioLevel;
    levelBar.style.width = `${Math.max(4, Math.round(level * 100))}%`;
  }, 80);
}

async function connect(): Promise<void> {
  connectButton.disabled = true;
  errorLabel.textContent = "";
  setStatus("Connecting…", true);

  try {
    const response = await fetch("/api/token", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ display_name: displayName.value || "Guest" }),
    });
    if (!response.ok) throw new Error(`Token request failed (${response.status})`);
    const credentials = (await response.json()) as TokenResponse;

    room = new Room({ adaptiveStream: true, dynacast: true });
    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === Track.Kind.Audio) attachAudio(track);
    });
    room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
      const speaker = participant?.identity === room?.localParticipant.identity ? "user" : "assistant";
      for (const segment of segments) {
        appendTranscript(segment.id, segment.text, speaker, segment.final);
      }
    });
    room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
      const agentSpeaking = speakers.some(
        (speaker) => speaker.identity !== room?.localParticipant.identity,
      );
      setStatus(agentSpeaking ? "Speaking" : "Listening", true);
    });
    room.on(RoomEvent.Disconnected, () => disconnect());

    await room.connect(credentials.url, credentials.token);
    await room.localParticipant.setMicrophoneEnabled(true);
    roomName.textContent = credentials.room;
    disconnectButton.disabled = false;
    displayName.disabled = true;
    setStatus("Listening", true);
    startLevelMeter(room);
  } catch (error) {
    showError(error);
    setStatus("Disconnected");
    connectButton.disabled = false;
    await room?.disconnect();
    room = undefined;
  }
}

function disconnect(): void {
  if (meterTimer) window.clearInterval(meterTimer);
  meterTimer = undefined;
  levelBar.style.width = "4%";
  room?.disconnect();
  room = undefined;
  roomName.textContent = "";
  connectButton.disabled = false;
  disconnectButton.disabled = true;
  displayName.disabled = false;
  setStatus("Disconnected");
}

connectButton.addEventListener("click", () => void connect());
disconnectButton.addEventListener("click", disconnect);
