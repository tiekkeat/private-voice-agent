import logging
from collections.abc import AsyncGenerator, AsyncIterable

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    ModelSettings,
    TurnHandlingOptions,
    cli,
    inference,
    metrics,
)
from livekit.plugins import openai, silero

from app.backends import OpenAICompatibleBackend
from app.config import get_settings
from app.language import contains_han, contains_latin_word, select_tts_voice
from app.logging_config import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("voice-core")

server = AgentServer()


class VoiceAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=settings.system_prompt)

    async def tts_node(
        self,
        text: AsyncIterable[str],
        model_settings: ModelSettings,
    ) -> AsyncGenerator[rtc.AudioFrame, None]:
        """Select an English or Mandarin Kokoro voice from the reply text."""
        iterator = text.__aiter__()
        buffered: list[str] = []
        preview = ""

        while len(preview.strip()) < 16:
            try:
                chunk = await anext(iterator)
            except StopAsyncIteration:
                break
            buffered.append(chunk)
            preview += chunk
            if contains_han(preview) or contains_latin_word(preview):
                break

        if not buffered:
            return

        voice = select_tts_voice(
            preview,
            english_voice=settings.tts_voice,
            chinese_voice=settings.tts_chinese_voice,
        )
        activity = self._get_activity_or_raise()
        activity.tts.update_options(voice=voice)
        logger.info("tts_voice_selected", extra={"voice": voice})

        async def replay_text() -> AsyncGenerator[str, None]:
            for chunk in buffered:
                yield chunk
            async for chunk in iterator:
                yield chunk

        async for frame in Agent.default.tts_node(self, replay_text(), model_settings):
            yield frame


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration=0.35,
        prefix_padding_duration=0.5,
    )


server.setup_fnc = prewarm


def _turn_handling() -> TurnHandlingOptions:
    if settings.turn_detector_mode == "vad":
        return TurnHandlingOptions(turn_detection="vad")

    return TurnHandlingOptions(
        turn_detection=inference.TurnDetector(
            version=settings.turn_detector_version,
            local_fallback=True,
        )
    )


@server.rtc_session()
async def voice_session(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name, "session_id": ctx.room.name}
    backend = OpenAICompatibleBackend(settings)

    session = AgentSession(
        stt=openai.STT(
            model=settings.stt_model,
            base_url=settings.stt_base_url,
            api_key="not-needed",
            detect_language=True,
        ),
        llm=backend.build_llm(),
        tts=openai.TTS(
            model=settings.tts_model,
            voice=settings.tts_voice,
            base_url=settings.tts_base_url,
            api_key="not-needed",
            response_format="pcm",
        ),
        vad=ctx.proc.userdata["vad"],
        turn_handling=_turn_handling(),
        preemptive_generation=True,
    )

    @session.on("metrics_collected")
    def on_metrics(event) -> None:  # type intentionally follows SDK event contract
        metrics.log_metrics(event.metrics)

    @session.on("user_input_transcribed")
    def on_transcript(event) -> None:  # type intentionally follows SDK event contract
        if event.is_final:
            logger.info("stt_final", extra={"transcript": event.transcript})

    @session.on("agent_state_changed")
    def on_agent_state(event) -> None:  # type intentionally follows SDK event contract
        logger.info("agent_state", extra={"state": str(event.new_state)})

    await session.start(room=ctx.room, agent=VoiceAssistant())
    await ctx.connect()
    logger.info(
        "session_started",
        extra={
            "backend": backend.name,
            "turn_detector": settings.turn_detector_mode,
        },
    )


if __name__ == "__main__":
    cli.run_app(server)
