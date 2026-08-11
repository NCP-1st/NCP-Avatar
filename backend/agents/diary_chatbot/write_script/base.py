"""Narration script agent contract."""

from abc import ABC, abstractmethod

from backend.agents.diary_chatbot.write_script.schemas import (
    NarrationScript,
    WriteScriptInput,
)


class ScriptGenerationAgent(ABC):
    """Generate a narration script preview from a completed diary."""

    @abstractmethod
    async def generate(
        self,
        data: WriteScriptInput,
        *,
        script_id: str | None = None,
    ) -> NarrationScript: ...
