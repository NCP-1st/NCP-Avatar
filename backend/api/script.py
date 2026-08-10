from fastapi import APIRouter

from backend.agents.diary_chatbot.write_script.agent import write_script
from backend.agents.diary_chatbot.write_script.schemas import (
    NarrationScript,
    WriteScriptInput,
)
from backend.config import load_config

router  = APIRouter(prefix="/script", tags = ["scripts"])


@router.post("/ai_script", response_model = NarrationScript)
async def create_script(payload: WriteScriptInput) -> NarrationScript:
    return await write_script(payload, load_config())
