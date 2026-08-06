from fastapi import APIRouter, Depends, HTTPException, status

from backend.dependencies import get_pipeline
from backend.orchestration.diary_pipeline import DiaryPipeline
from backend.api.schemas import (
    AddInputsRequest,
    CreateSessionRequest,
    DiarySession,
    PreprocessResult,
)

router = APIRouter(prefix="/diary", tags=["diary"])


def require_session(session_id: str, pipeline: DiaryPipeline) -> None:
    if session_id not in pipeline.repo.sessions:
        raise HTTPException(status_code=404, detail="diary session not found")


@router.post("/sessions", response_model=DiarySession, status_code=status.HTTP_201_CREATED)
def create_session(request: CreateSessionRequest, pipeline: DiaryPipeline = Depends(get_pipeline)) -> DiarySession:
    return pipeline.create_session(request.user_id, request.diary_date)


@router.post("/{session_id}/inputs", response_model=PreprocessResult)
async def add_inputs(session_id: str, request: AddInputsRequest,
                     pipeline: DiaryPipeline = Depends(get_pipeline)) -> PreprocessResult:
    require_session(session_id, pipeline)
    return await pipeline.preprocess(session_id, request.items)
