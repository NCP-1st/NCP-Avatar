

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.agents.counsel_chatbot import CounselReply, CounselRequest
from backend.dependencies import get_counsel_flow
from backend.orchestration.counsel_flow import CounselFlow

router = APIRouter(prefix="/counsel", tags=["counsel"])


@router.post("/chat", response_model=CounselReply)
async def counsel_chat(
    request: CounselRequest,
    flow: Annotated[CounselFlow, Depends(get_counsel_flow)],
) -> CounselReply:

    try:
        return await flow.run(request)
    except PermissionError as exc:
        # 남의 counsel_id 로 대화에 끼어들려는 요청. 저장소가 이미 막았으므로
        # 아무것도 저장되지 않았다. 서버 장애(500)가 아니라 거절(403)이다.
        #
        # 세션이 있는지 없는지는 알려주지 않는다 — 404와 403을 갈라 주면
        # counsel_id 를 훑어 남의 세션 존재 여부를 알아낼 수 있다.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="이 상담 세션에 접근할 수 없습니다",
        ) from exc
