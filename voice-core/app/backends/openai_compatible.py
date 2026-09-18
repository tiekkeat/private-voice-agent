from livekit.agents import llm
from livekit.plugins import openai

from app.backends.base import AgentBackend
from app.config import Settings


class OpenAICompatibleBackend(AgentBackend):
    name = "openai_compatible"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def build_llm(self) -> llm.LLM:
        return openai.LLM(
            model=self._settings.llm_model,
            base_url=self._settings.llm_base_url,
            api_key=self._settings.llm_api_key,
        )
