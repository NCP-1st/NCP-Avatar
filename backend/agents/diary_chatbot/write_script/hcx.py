"""HCX-007 narration script agent."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.agents.diary_chatbot.write_script.base import ScriptGenerationAgent
from backend.agents.diary_chatbot.write_script.prompt import build_script_messages
from backend.agents.diary_chatbot.write_script.schemas import (
    Emotion,
    NarrationScript,
    WriteScriptInput,
)
from backend.services.llm import LLMRequest, LLMResponse, generate_llm

GenerateFunction = Callable[[LLMRequest, dict[str, Any]], Awaitable[LLMResponse]]


class _NarrationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narration_text: str = Field(min_length=1)
    emotion: Emotion


class Hcx007ScriptGenerationAgent(ScriptGenerationAgent):
    def __init__(
        self,
        config: dict[str, Any],
        *,
        generate: GenerateFunction = generate_llm,
    ) -> None:
        self._config = config
        self._generate = generate

    async def generate(
        self,
        data: WriteScriptInput,
        *,
        script_id: str | None = None,
    ) -> NarrationScript:
        response = await self._generate(
            LLMRequest(
                model=self._config["llm"]["model_reasoning"],
                messages=build_script_messages(data),
                response_schema=_NarrationDraft.model_json_schema(),
                temperature=0.3,
                max_tokens=512,
            ),
            self._config,
        )
        draft = _NarrationDraft.model_validate_json(response.content)

        return NarrationScript(
            script_id=script_id or f"script_{uuid4().hex[:12]}",
            diary_id=data.diary_id,
            narration_text=draft.narration_text.strip(),
            target_duration_seconds=data.script_options.target_duration_seconds,
            emotion=draft.emotion,
        )
