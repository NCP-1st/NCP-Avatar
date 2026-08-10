from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.agents.diary_chatbot.write_script.prompt import ( build_script_messages )
from backend.agents.diary_chatbot.write_script.schemas import (Emotion, NarrationScript , WriteScriptInput)
from backend.services.llm import LLMRequest, generate_llm

class _NarrationDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')

    narration_text :str = Field(min_length = 1)
    emotion : Emotion

async def write_script(
        data: WriteScriptInput,
        config: dict[str,Any],
        *,
        script_id : str | None = None,
)-> NarrationScript:
    """ 승인된 일기만 나레이션 진행"""

    if not data.approved:
        raise ValueError("승인된 일기만 대본을 생성할 수 있습니다.")

    request = LLMRequest(
        model = config['llm']['model_reasoning'],
        messages = build_script_messages(data),
        response_schema = _NarrationDraft.model_json_schema(),
        temperature = 0.3,
        max_tokens=512,
    )

    response = await generate_llm(request, config)
    draft = _NarrationDraft.model_validate_json(response.content)

    return NarrationScript(
        script_id = script_id or f"script_{uuid4().hex[:12]}",
        diary_id =data.diary_id,
        narration_text = draft.narration_text.strip(),
        target_duration_seconds = (
            data.script_options.target_duration_seconds
        ),
        emotion = draft.emotion,
    )
