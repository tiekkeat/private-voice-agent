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
from app.language import select_tts_voice, split_tts_segments
from app.logging_config import configure_logging
from app.speech import stt_language_options

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
        """Stream sentence-sized English, Mandarin, and Malay TTS segments."""
        activity = self._get_activity_or_raise()

        async def speak(sentence: str) -> AsyncGenerator[rtc.AudioFrame, None]:
            for segment in split_tts_segments(sentence):
                if not segment.text.strip():
                    continue
                voice = select_tts_voice(
                    segment.text,
                    english_voice=settings.tts_voice,
                    chinese_voice=settings.tts_chinese_voice,
                    malay_voice=settings.tts_malay_voice,
                )
                activity.tts.update_options(voice=voice)
                logger.info(
                    "tts_voice_selected",
                    extra={"voice": voice, "language": segment.language},
                )

                async def one_segment(
                    value: str = segment.text,
                ) -> AsyncGenerator[str, None]:
                    yield value

                async for frame in Agent.default.tts_node(
                    self, one_segment(), model_settings
                ):
                    yield frame

        buffer = ""
        async for chunk in text:
            buffer += chunk
            while True:
                boundary = next(
                    (index + 1 for index, char in enumerate(buffer) if char in ".!?。！？"),
                    None,
                )
                if boundary is None:
                    break
                sentence, buffer = buffer[:boundary], buffer[boundary:]
                async for frame in speak(sentence):
                    yield frame

            if len(buffer) >= 180 and " " in buffer:
                boundary = buffer.rfind(" ", 0, 180)
                sentence, buffer = buffer[:boundary], buffer[boundary:]
                async for frame in speak(sentence):
                    yield frame

        if buffer.strip():
            async for frame in speak(buffer):
                yield frame


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load(
        min_silence_duration=0.35,
        prefix_padding_duration=0.5,
    )


server.setup_fnc = prewarm


def _turn_handling() -> TurnHandlingOptions:
    if settings.turn_detector_mode == "vad":
        turn_detector = "vad"
    else:
        turn_detector = inference.TurnDetector(
            version=settings.turn_detector_version,
            local_fallback=True,
        )

    return TurnHandlingOptions(
        turn_detection=turn_detector,
        interruption={
            "mode": "vad",
            "min_duration": settings.interruption_min_duration,
            "min_words": settings.interruption_min_words,
            "false_interruption_timeout": settings.false_interruption_timeout,
            "resume_false_interruption": settings.resume_false_interruption,
        },
        preemptive_generation={"enabled": True},
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
            **stt_language_options(settings.stt_language, settings.stt_prompt),
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
            "stt_language": settings.stt_language,
            "interruption_min_duration": settings.interruption_min_duration,
            "interruption_min_words": settings.interruption_min_words,
        },
    )


if __name__ == "__main__":
    cli.run_app(server)
