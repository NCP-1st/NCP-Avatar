

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.agents.counsel_chatbot import (
    CounselHistory,
    CounselReply,
    CounselRequest,
    CounselSessionSummary,
)
from backend.dependencies import get_counsel_flow, get_counsel_store
from backend.orchestration.counsel_flow import CounselFlow
from backend.repositories import ConversationStore

router = APIRouter(prefix="/counsel", tags=["counsel"])

_SESSION_LIST_MAX = 50


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


@router.get("/sessions", response_model=list[CounselSessionSummary])
async def list_counsel_sessions(
    store: Annotated[ConversationStore, Depends(get_counsel_store)],
    user_id: str = Query(..., description="조회할 사용자"),
    limit: int = Query(20, ge=1, le=_SESSION_LIST_MAX),
) -> list[CounselSessionSummary]:
    """지난 상담 목록. 최근 활동 순.

    대화 내용은 담기지 않는다 — 목록에 필요한 건 제목과 시각뿐이고, 지난
    상담 스무 개의 본문을 매번 내려보낼 이유가 없다.
    """
    return await store.list_sessions(user_id=user_id, limit=limit)


@router.get("/sessions/{counsel_id}", response_model=CounselHistory)
async def get_counsel_session(
    counsel_id: str,
    store: Annotated[ConversationStore, Depends(get_counsel_store)],
    user_id: str = Query(..., description="세션 소유자"),
) -> CounselHistory:
    """지난 상담 하나를 통째로. 이어서 대화하려면 이 `counsel_id`로 chat 을 부른다."""
    try:
        return await store.load_history(counsel_id=counsel_id, user_id=user_id)
    except PermissionError as exc:
        # 없는 상담도 403이다. 404와 갈라 주면 counsel_id 를 훑어 남의 세션
        # 존재 여부를 알아낼 수 있다 — chat 엔드포인트와 같은 규칙이다.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="이 상담 세션에 접근할 수 없습니다",
        ) from exc
