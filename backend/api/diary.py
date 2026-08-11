import asyncio
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas import (
    AddInputsRequest,
    ApproveDiaryRequest,
    ConfirmTranscriptRequest,
    ConfirmTranscriptResponse,
    CreateSessionRequest,
    DiaryChatRequest,
    DiaryChatResponse,
    DiaryReviewRequest,
    DiaryReviewResponse,
    DiarySession,
    GenerationJobResponse,
    GenerationJobStatus,
    InputType,
    PreprocessResult,
    ProcessingStatus,
)
from backend.dependencies import (
    diary_states,
    generation_jobs,
    generation_tasks,
    get_diary_media_orchestrator,
    get_diary_orchestrator,
    get_pipeline,
    media_jobs,
    media_tasks,
)
from backend.orchestration.diary_media import DiaryMediaOrchestrator
from backend.orchestration.diary_orchestrator import DiaryOrchestrator
from backend.orchestration.diary_pipeline import DiaryPipeline
from backend.repositories.sqlalchemy import SQLAlchemyDiaryRepository
from database.conn.db import AsyncSessionLocal, get_db

router = APIRouter(prefix="/diary", tags=["diary"])


def require_session(session_id: str, pipeline: DiaryPipeline) -> None:
    if session_id not in pipeline.repo.sessions:
        raise HTTPException(status_code=404, detail="diary session not found")


@router.post("/sessions", response_model=DiarySession, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    pipeline: DiaryPipeline = Depends(get_pipeline),
    db: AsyncSession = Depends(get_db),
) -> DiarySession:
    session = pipeline.create_session(request.user_id, request.diary_date)
    diary_states.pop(session.session_id, None)
    try:
        await SQLAlchemyDiaryRepository(db).save_session(
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
    voice_id: str,
    target_duration_seconds: int,
    tone: str,
    orchestrator: DiaryMediaOrchestrator,
) -> None:
    media_jobs[job_id]["status"] = "processing"
    try:
        async with AsyncSessionLocal() as db:
            result = await orchestrator.run(
                version_id=version_id,
                voice_id=voice_id,
                target_duration_seconds=target_duration_seconds,
                tone=tone,
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
        )


@router.post("/{session_id}/inputs", response_model=PreprocessResult)
async def add_inputs(
    session_id: str,
    request: AddInputsRequest,
    pipeline: DiaryPipeline = Depends(get_pipeline),
    db: AsyncSession = Depends(get_db),
) -> PreprocessResult:
    require_session(session_id, pipeline)
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
    require_session(session_id, pipeline)
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
    require_session(session_id, pipeline)
    state = diary_states.setdefault(session_id, orchestrator.start_session(session_id))
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
    try:
        await orchestrator.handle_turn(
            state,
            message=request.message,
            image_urls=image_urls,
            audio_transcripts=audio_transcripts,
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
    session = pipeline.repo.sessions[session_id]
    persistence = SQLAlchemyDiaryRepository(db)
    assistant_text = state.latest_turn.reaction
    if state.latest_turn.follow_up_questions:
        assistant_text += "\n" + state.latest_turn.follow_up_questions[0]
    await persistence.save_chat_turn(
        session_id=session_id,
        user_id=session.user_id,
        user_chat=request.message,
        assistant_chat=assistant_text,
    )
    return DiaryChatResponse(
        session_id=session_id,
        stage=state.stage.value,
        questions_asked_count=state.questions_asked_count,
        turn=state.latest_turn.model_dump(),
        review_summary=state.review_summary,
    )


@router.post("/{session_id}/review", response_model=DiaryReviewResponse)
def review_diary_information(
    session_id: str,
    request: DiaryReviewRequest,
    pipeline: DiaryPipeline = Depends(get_pipeline),
    orchestrator: DiaryOrchestrator = Depends(get_diary_orchestrator),
) -> DiaryReviewResponse:
    require_session(session_id, pipeline)
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
) -> GenerationJobResponse:
    require_session(session_id, pipeline)
    state = diary_states.get(session_id)
    if state is None or state.stage.value != "ready_to_generate":
        raise HTTPException(status_code=409, detail="추가 대화를 먼저 완료해 주세요.")
    job_id = str(uuid4())
    generation_jobs[job_id] = {"job_id": job_id, "status": "queued", "result": None}

    task = asyncio.create_task(_run_generation_job(job_id, state, orchestrator))
    generation_tasks.add(task)
    task.add_done_callback(generation_tasks.discard)
    return GenerationJobResponse(job_id=job_id, status="queued")


@router.post(
    "/versions/{version_id}/approve",
    response_model=GenerationJobResponse,
    status_code=202,
)
async def approve_diary_and_generate_media(
    version_id: str,
    request: ApproveDiaryRequest,
    media_orchestrator: DiaryMediaOrchestrator = Depends(
        get_diary_media_orchestrator
    ),
    db: AsyncSession = Depends(get_db),
) -> GenerationJobResponse:
    repository = SQLAlchemyDiaryRepository(db)
    approved = await repository.approve_version(version_id)
    if not approved:
        raise HTTPException(status_code=404, detail="diary version not found")

    job_id = str(uuid4())
    media_jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "result": None,
        "error_code": None,
    }
    task = asyncio.create_task(
        _run_media_job(
            job_id,
            version_id=version_id,
            voice_id=request.voice_id,
            target_duration_seconds=request.target_duration_seconds,
            tone=request.tone,
            orchestrator=media_orchestrator,
        )
    )
    media_tasks.add(task)
    task.add_done_callback(media_tasks.discard)
    return GenerationJobResponse(job_id=job_id, status="queued")


@router.get("/jobs/{job_id}", response_model=GenerationJobStatus)
def get_generation_job(job_id: str) -> GenerationJobStatus:
    job = generation_jobs.get(job_id) or media_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="generation job not found")
    return GenerationJobStatus.model_validate(job)
