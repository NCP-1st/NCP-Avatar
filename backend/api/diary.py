import asyncio
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.diary_chatbot.models import WorkflowStage
from backend.api.schemas import (
    AddInputsRequest,
    ConfirmTranscriptRequest,
    ConfirmTranscriptResponse,
    CreateSessionRequest,
    DiaryApprovalResponse,
    DiaryApprovalRequest,
    DiaryChatRequest,
    DiaryChatResponse,
    DiaryReviewRequest,
    DiaryReviewResponse,
    DiarySession,
    DiaryVersionListResponse,
    DiaryVersionResponse,
    GenerationJobResponse,
    GenerationJobStatus,
    InputType,
    NormalizedInputItem,
    NewVersionChatResponse,
    PreprocessResult,
    ProcessingStatus,
)
from backend.dependencies import (
    diary_states,
    generation_jobs,
    generation_tasks,
    get_diary_media_orchestrator,
    get_diary_deletion_orchestrator,
    get_diary_embedding_service,
    get_diary_orchestrator,
    get_media_storage_adapter,
    get_pipeline,
    media_jobs,
    media_tasks,
)
from backend.orchestration.diary_deletion import (
    DiaryDeletionOrchestrator,
    DiaryMediaProcessingError,
)
from backend.orchestration.diary_media import DiaryMediaOrchestrator
from backend.orchestration.diary_orchestrator import (
    MAX_DIARY_VERSIONS,
    DiaryOrchestrator,
)
from backend.services.storage import StorageAdapter
from backend.services.embedding import DiaryEmbeddingService
from backend.orchestration.diary_pipeline import DiaryPipeline
from backend.repositories.sqlalchemy import SQLAlchemyDiaryRepository
from database.conn.db import AsyncSessionLocal, get_db
from database.models import DiarySession as ORMDiarySession

router = APIRouter(prefix="/diary", tags=["diary"])


async def require_session(
    session_id: str,
    pipeline: DiaryPipeline,
    db: AsyncSession,
) -> DiarySession:
    cached = pipeline.repo.sessions.get(session_id)
    if cached is not None:
        return cached
    stored = await db.get(ORMDiarySession, session_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="diary session not found")
    restored = DiarySession(
        session_id=stored.session_id,
        user_id=stored.user_id,
        diary_date=stored.diary_date,
        status=stored.status,
    )
    pipeline.repo.sessions[session_id] = restored
    return restored


@router.post("/sessions", response_model=DiarySession, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    pipeline: DiaryPipeline = Depends(get_pipeline),
    db: AsyncSession = Depends(get_db),
) -> DiarySession:
    repo = SQLAlchemyDiaryRepository(db)
    existing_session_id = await repo.find_existing_session(
        user_id=request.user_id, diary_date=request.diary_date
    )
    if existing_session_id is not None:
        if existing_session_id not in pipeline.repo.sessions:
            pipeline.repo.sessions[existing_session_id] = DiarySession(
                session_id=existing_session_id,
                user_id=request.user_id,
                diary_date=request.diary_date,
            )
        return pipeline.repo.sessions[existing_session_id]

    session = pipeline.create_session(request.user_id, request.diary_date)
    diary_states.pop(session.session_id, None)
    try:
        await repo.save_session(
            user_id=request.user_id,
            diary_date=request.diary_date,
            session_id=session.session_id,
        )
    except Exception:
        pipeline.repo.sessions.pop(session.session_id, None)
        await db.rollback()
        raise
    return session


async def _run_generation_job(
    job_id: str,
    state,
    orchestrator: DiaryOrchestrator,
) -> None:
    generation_jobs[job_id]["status"] = "processing"
    try:
        version = await orchestrator.request_generation(state)
        async with AsyncSessionLocal() as db:
            try:
                await SQLAlchemyDiaryRepository(db).save_version(version)
            except Exception:
                await db.rollback()
                raise
        generation_jobs[job_id].update(status="completed", result=version.model_dump())
    except Exception as exc:
        generation_jobs[job_id].update(status="failed", error_code=type(exc).__name__)


async def _run_media_job(
    job_id: str,
    *,
    version_id: str,
    character_id: str,
    voice_id: str,
    orchestrator: DiaryMediaOrchestrator,
) -> None:
    media_jobs[job_id]["status"] = "processing"
    try:
        async with AsyncSessionLocal() as db:
            result = await orchestrator.run(
                version_id=version_id,
                voice_id=voice_id,
                character_id=character_id,
                character_image_path=(
                    Path(__file__).resolve().parents[1]
                    / "character"
                    / f"{character_id}.png"
                ),
                target_duration_seconds=10,
                tone="따뜻한 회상",
                repository=SQLAlchemyDiaryRepository(db),
            )
        media_jobs[job_id].update(
            status="completed",
            result=result.model_dump(),
        )
    except Exception as exc:
        media_jobs[job_id].update(
            status="failed",
            error_code=type(exc).__name__,
            error_message=str(exc)[:500],
        )


@router.post("/{session_id}/inputs", response_model=PreprocessResult)
async def add_inputs(
    session_id: str,
    request: AddInputsRequest,
    pipeline: DiaryPipeline = Depends(get_pipeline),
    db: AsyncSession = Depends(get_db),
) -> PreprocessResult:
    await require_session(session_id, pipeline, db)
    result = await pipeline.preprocess(session_id, request.items)
    await SQLAlchemyDiaryRepository(db).save_inputs(
        session_id=session_id, items=result.items
    )
    return result


@router.put(
    "/{session_id}/inputs/{input_id}/transcript",
    response_model=ConfirmTranscriptResponse,
)
async def confirm_audio_transcript(
    session_id: str,
    input_id: str,
    request: ConfirmTranscriptRequest,
    pipeline: DiaryPipeline = Depends(get_pipeline),
    db: AsyncSession = Depends(get_db),
) -> ConfirmTranscriptResponse:
    await require_session(session_id, pipeline, db)
    item = next(
        (
            stored
            for stored in pipeline.repo.inputs.get(session_id, [])
            if stored.input_id == input_id
        ),
        None,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="audio input not found")
    if item.type is not InputType.AUDIO or item.status is not ProcessingStatus.OK:
        raise HTTPException(status_code=409, detail="확정할 수 있는 음성 입력이 아닙니다.")
    item.transcript = request.transcript
    item.transcript_confirmed = True
    await SQLAlchemyDiaryRepository(db).update_transcript(
        input_id=input_id, transcript=item.transcript
    )
    return ConfirmTranscriptResponse(
        session_id=session_id,
        input_id=input_id,
        transcript=item.transcript,
        transcript_confirmed=True,
    )


@router.post("/{session_id}/chat", response_model=DiaryChatResponse)
async def chat(
    session_id: str,
    request: DiaryChatRequest,
    pipeline: DiaryPipeline = Depends(get_pipeline),
    orchestrator: DiaryOrchestrator = Depends(get_diary_orchestrator),
    db: AsyncSession = Depends(get_db),
) -> DiaryChatResponse:
    await require_session(session_id, pipeline, db)
    state = diary_states.setdefault(session_id, orchestrator.start_session(session_id))
    if state.stage in {
        WorkflowStage.DRAFTED,
        WorkflowStage.APPROVED,
        WorkflowStage.RENDERING,
        WorkflowStage.COMPLETED,
    }:
        raise HTTPException(
            status_code=409,
            detail="이 일기 채팅은 종료되었습니다. '새 일기 쓰기'로 새 채팅을 시작해 주세요.",
        )

    requested_ids = set(request.input_ids)
    available = {
        item.input_id: item
        for item in pipeline.repo.inputs.get(session_id, [])
        if item.input_id in requested_ids and item.status is ProcessingStatus.OK
    }
    missing_ids = requested_ids - set(available)
    if missing_ids:
        raise HTTPException(status_code=400, detail="전처리되지 않은 첨부 입력이 있습니다.")
    unconfirmed_audio_ids = {
        input_id
        for input_id, item in available.items()
        if item.type is InputType.AUDIO and not item.transcript_confirmed
    }
    if unconfirmed_audio_ids:
        raise HTTPException(
            status_code=409,
            detail="음성 메모의 인식 결과를 먼저 확인해 주세요.",
        )
    image_urls = {
        input_id: item.storage_url
        for input_id, item in available.items()
        if item.type is InputType.PHOTO and item.storage_url
    }
    audio_transcripts = {
        input_id: item.transcript
        for input_id, item in available.items()
        if item.type is InputType.AUDIO and item.transcript
    }
    text_input_id = f"turn-{uuid4()}" if request.message.strip() else None
    try:
        await orchestrator.handle_turn(
            state,
            message=request.message,
            image_urls=image_urls,
            audio_transcripts=audio_transcripts,
            text_input_id=text_input_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "챗봇 응답 생성에 실패했습니다.",
                "error_code": type(exc).__name__,
            },
        ) from exc

    if state.latest_turn is None:
        raise HTTPException(status_code=409, detail="이미 일기 생성 준비가 완료되었습니다.")

    persistence = SQLAlchemyDiaryRepository(db)
    if text_input_id is not None:
        await persistence.save_inputs(
            session_id=session_id,
            items=[
                NormalizedInputItem(
                    input_id=text_input_id,
                    type=InputType.TEXT,
                    transcript=request.message.strip(),
                    status=ProcessingStatus.OK,
                )
            ],
        )
    return DiaryChatResponse(
        session_id=session_id,
        stage=state.stage.value,
        questions_asked_count=state.questions_asked_count,
        turn=state.latest_turn.model_dump(),
        review_summary=state.review_summary,
    )


@router.post("/{session_id}/review", response_model=DiaryReviewResponse)
async def review_diary_information(
    session_id: str,
    request: DiaryReviewRequest,
    pipeline: DiaryPipeline = Depends(get_pipeline),
    orchestrator: DiaryOrchestrator = Depends(get_diary_orchestrator),
    db: AsyncSession = Depends(get_db),
) -> DiaryReviewResponse:
    await require_session(session_id, pipeline, db)
    state = diary_states.get(session_id)
    if state is None:
        raise HTTPException(status_code=409, detail="먼저 일기 대화를 진행해 주세요.")
    try:
        if request.action == "skip_current":
            orchestrator.skip_current_question(state)
        elif request.action == "summary_yes":
            orchestrator.review_summary(state, correct=True)
        elif request.action == "summary_no":
            orchestrator.review_summary(state, correct=False)
        elif request.action == "more_yes":
            orchestrator.choose_more_content(state, wants_more=True)
        else:
            orchestrator.choose_more_content(state, wants_more=False)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return DiaryReviewResponse(
        session_id=session_id,
        stage=state.stage.value,
        review_summary=state.review_summary,
        turn=(
            state.latest_turn.model_dump()
            if request.action == "skip_current"
            and state.stage.value == "needs_clarification"
            and state.latest_turn
            else None
        ),
    )


@router.post("/{session_id}/generate", response_model=GenerationJobResponse, status_code=202)
async def generate_diary(
    session_id: str,
    pipeline: DiaryPipeline = Depends(get_pipeline),
    orchestrator: DiaryOrchestrator = Depends(get_diary_orchestrator),
    db: AsyncSession = Depends(get_db),
) -> GenerationJobResponse:
    await require_session(session_id, pipeline, db)
    state = diary_states.get(session_id)
    if state is None or state.stage.value != "ready_to_generate":
        raise HTTPException(status_code=409, detail="추가 대화를 먼저 완료해 주세요.")
    job_id = str(uuid4())
    generation_jobs[job_id] = {"job_id": job_id, "status": "queued", "result": None}

    task = asyncio.create_task(_run_generation_job(job_id, state, orchestrator))
    generation_tasks.add(task)
    task.add_done_callback(generation_tasks.discard)
    return GenerationJobResponse(job_id=job_id, status="queued")


@router.get(
    "/{session_id}/versions",
    response_model=DiaryVersionListResponse,
)
async def list_diary_versions(
    session_id: str,
    pipeline: DiaryPipeline = Depends(get_pipeline),
    db: AsyncSession = Depends(get_db),
) -> DiaryVersionListResponse:
    await require_session(session_id, pipeline, db)
    versions = await SQLAlchemyDiaryRepository(db).get_versions(session_id)
    return DiaryVersionListResponse(
        session_id=session_id,
        versions=[
            DiaryVersionResponse.model_validate(version.model_dump())
            for version in versions
        ],
        max_versions=MAX_DIARY_VERSIONS,
        can_create_new_version=len(versions) < MAX_DIARY_VERSIONS,
    )


@router.post(
    "/{session_id}/versions/new-chat",
    response_model=NewVersionChatResponse,
)
async def start_new_version_chat(
    session_id: str,
    pipeline: DiaryPipeline = Depends(get_pipeline),
    orchestrator: DiaryOrchestrator = Depends(get_diary_orchestrator),
    db: AsyncSession = Depends(get_db),
) -> NewVersionChatResponse:
    await require_session(session_id, pipeline, db)
    versions = await SQLAlchemyDiaryRepository(db).get_versions(session_id)
    if len(versions) >= MAX_DIARY_VERSIONS:
        raise HTTPException(
            status_code=409,
            detail=(
                "일기는 최대 3개까지 생성할 수 있어요. "
                "일기 후보 중 하나를 삭제하고 다시 써보세요."
            ),
        )
    state = diary_states.setdefault(session_id, orchestrator.start_session(session_id))
    state.versions = versions
    orchestrator.start_new_version_chat(state)
    await SQLAlchemyDiaryRepository(db).mark_session_active(session_id)
    return NewVersionChatResponse(session_id=session_id, stage=state.stage.value)


@router.delete("/{session_id}/versions/{version_id}")
async def delete_diary_version(
    session_id: str,
    version_id: str,
    pipeline: DiaryPipeline = Depends(get_pipeline),
    deletion_orchestrator: DiaryDeletionOrchestrator = Depends(
        get_diary_deletion_orchestrator
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | int]:
    await require_session(session_id, pipeline, db)
    if any(
        job.get("version_id") == version_id
        and job.get("status") in {"queued", "processing"}
        for job in media_jobs.values()
    ):
        raise HTTPException(
            status_code=409,
            detail="media generation is still processing",
        )
    try:
        deletion = await deletion_orchestrator.delete_version(
            session_id=session_id,
            version_id=version_id,
            repository=SQLAlchemyDiaryRepository(db),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DiaryMediaProcessingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "failed to delete diary media from storage",
                "error_code": type(exc).__name__,
            },
        ) from exc

    state = diary_states.get(session_id)
    if state is not None:
        state.versions = [
            item for item in state.versions if item.version_id != version_id
        ]
    return {
        "deleted_version_id": version_id,
        "deleted_object_count": deletion.deleted_object_count,
    }


@router.get("/{session_id}/versions/{version_id}/video")
async def stream_avatar_video(
    session_id: str,
    version_id: str,
    pipeline: DiaryPipeline = Depends(get_pipeline),
    storage: StorageAdapter = Depends(get_media_storage_adapter),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Serve a stored avatar video without requiring a public storage bucket."""
    await require_session(session_id, pipeline, db)
    repository = SQLAlchemyDiaryRepository(db)
    version = await repository.get_version(version_id)
    if version is None or version.session_id != session_id:
        raise HTTPException(status_code=404, detail="diary version not found")

    video = await repository.get_avatar_video(version_id)
    if video is None or video.status != "completed" or not video.object_key:
        raise HTTPException(status_code=404, detail="completed avatar video not found")

    try:
        video_bytes = await storage.download(object_name=video.object_key)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "failed to download avatar video from storage",
                "error_code": type(exc).__name__,
            },
        ) from exc

    return Response(
        content=video_bytes,
        media_type=video.video_mime_type or "video/mp4",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.post(
    "/{session_id}/versions/{version_id}/approve",
    response_model=DiaryApprovalResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def approve_diary_version(
    session_id: str,
    version_id: str,
    request: DiaryApprovalRequest,
    pipeline: DiaryPipeline = Depends(get_pipeline),
    orchestrator: DiaryOrchestrator = Depends(get_diary_orchestrator),
    media_orchestrator: DiaryMediaOrchestrator = Depends(
        get_diary_media_orchestrator
    ),
    embedding_service: DiaryEmbeddingService = Depends(
        get_diary_embedding_service
    ),
    db: AsyncSession = Depends(get_db),
) -> DiaryApprovalResponse:
    await require_session(session_id, pipeline, db)
    repository = SQLAlchemyDiaryRepository(db)
    try:
        selected = await repository.finalize_session_versions(
            session_id=session_id,
            approved_version_id=version_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    state = diary_states.get(session_id)
    if state is None:
        state = orchestrator.start_session(session_id)
        diary_states[session_id] = state
    state.versions = await repository.get_versions(session_id)
    in_memory = next(
        item for item in state.versions if item.version_id == version_id
    )
    selected = await orchestrator.approve(
        state,
        in_memory,
        embedding_service=embedding_service,
    )

    job_id = str(uuid4())
    media_jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "result": None,
        "error_code": None,
        "error_message": None,
        "version_id": version_id,
    }
    task = asyncio.create_task(
        _run_media_job(
            job_id,
            version_id=version_id,
            character_id=request.character_id,
            voice_id=request.voice_id,
            orchestrator=media_orchestrator,
        )
    )
    media_tasks.add(task)
    task.add_done_callback(media_tasks.discard)

    return DiaryApprovalResponse(
        **selected.model_dump(),
        media_job_id=job_id,
        media_status="queued",
    )


@router.get("/jobs/{job_id}", response_model=GenerationJobStatus)
def get_generation_job(job_id: str) -> GenerationJobStatus:
    job = generation_jobs.get(job_id) or media_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="generation job not found")
    return GenerationJobStatus.model_validate(job)
