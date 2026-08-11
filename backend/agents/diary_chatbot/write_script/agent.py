from __future__ import annotations

from typing import Any

from backend.agents.diary_chatbot.write_script.hcx import Hcx007ScriptGenerationAgent
from backend.agents.diary_chatbot.write_script.schemas import (
    NarrationScript,
    WriteScriptInput,
)


async def write_script(
    data: WriteScriptInput,
    config: dict[str, Any],
    *,
    script_id: str | None = None,
) -> NarrationScript:
    """Compatibility function used by the current API and manual test."""
    agent = Hcx007ScriptGenerationAgent(config)
    return await agent.generate(data, script_id=script_id)
