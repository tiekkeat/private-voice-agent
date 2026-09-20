from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    livekit_url: str = "ws://livekit:7880"
    livekit_api_key: str
    livekit_api_secret: str = Field(min_length=32)
    public_livekit_url: str

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str
    llm_model: str

    stt_base_url: str = "http://faster-whisper:8000/v1"
    stt_model: str = "Systran/faster-whisper-small"
    stt_language: Literal["auto", "en", "zh", "ms"] = "auto"
    stt_prompt: str = (
        "The speaker may code-switch between Malaysian English, Mandarin Chinese, "
        "and Malay. Preserve each spoken language and transcribe Mandarin as Simplified "
        "Chinese. Ignore coughs, breathing, and other non-speech sounds."
    )
    tts_base_url: str = "http://kokoro:8880/v1"
    tts_model: str = "kokoro"
    tts_voice: str = "af_heart"
    tts_chinese_voice: str = "zf_xiaoxiao"
    tts_malay_voice: str = "af_heart"

    turn_detector_mode: Literal["v1-mini", "vad"] = "v1-mini"
    turn_detector_version: str = "v1-mini"
    interruption_min_duration: float = Field(default=0.8, ge=0.1, le=5.0)
    interruption_min_words: int = Field(default=1, ge=0, le=10)
    false_interruption_timeout: float = Field(default=1.5, ge=0.1, le=10.0)
    resume_false_interruption: bool = True

    system_prompt: str = (
        "You are a concise, friendly voice assistant. Reply in the user's requested "
        "language. Otherwise naturally follow the user's mix of Malaysian English, "
        "Mandarin Chinese, and Malay, with English as fallback. Keep most replies to one "
        "or two short sentences. Avoid markdown because your response will be spoken aloud."
    )
    deployment_mode: Literal["cpu", "gpu"] = "cpu"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    tts_device: str = "cpu"
    log_level: str = "INFO"

    @field_validator("llm_base_url", "stt_base_url", "tts_base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        return value.rstrip("/")

@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
