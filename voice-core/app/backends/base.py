from abc import ABC, abstractmethod

from livekit.agents import llm


class AgentBackend(ABC):
    """Small provider boundary kept stable for the future OpenClaw adapter."""

    name: str

    @abstractmethod
    def build_llm(self) -> llm.LLM:
        """Build the streaming model used by a single isolated AgentSession."""
