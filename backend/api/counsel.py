

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.agents.counsel_chatbot import CounselReply, CounselRequest
from backend.dependencies import get_counsel_flow
from backend.orchestration.counsel_flow import CounselFlow

router = APIRouter(prefix="/counsel", tags=["counsel"])


@router.post("/chat", response_model=CounselReply)
async def counsel_chat(
    request: CounselRequest,
    flow: Annotated[CounselFlow, Depends(get_counsel_flow)],
) -> CounselReply:

    return await flow.run(request)
