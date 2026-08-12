import asyncio
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.counsel_chatbot import ContextAgent, CounselorAgent
from backend.agents.diary_chatbot import Hcx005MultimodalChatAgent, Hcx007DiaryGenerationAgent
from backend.agents.diary_chatbot.write_script import Hcx007ScriptGenerationAgent
from backend.config import load_config
from backend.orchestration.counsel_flow import CounselFlow
from backend.orchestration.diary_media import DiaryMediaOrchestrator
from backend.orchestration.diary_deletion import DiaryDeletionOrchestrator
from backend.orchestration.diary_orchestrator import DiaryOrchestrationState, DiaryOrchestrator
from backend.orchestration.diary_pipeline import DiaryPipeline
from backend.repositories import (
    ConversationStore,
    InMemoryDiaryRepository,
    SQLAlchemyConversationStore,
)
from backend.services.knowledge import (
    DiaryMemoryPort,
    DiaryThresholds,
    InMemoryCounselKnowledge,
    InMemoryPersonalOntology,
    SqlDiaryMemory,
)
from backend.services.avatar import HuggingFaceSpaceAvatarAdapter
from backend.services.speech.clova import ClovaSpeechToTextAdapter
from backend.services.storage import NcpObjectStorageAdapter, StorageAdapter
from backend.services.storage.inline import InlineDataUrlStorageAdapter
from database.conn.db import get_db
from backend.services.voice import ClovaVoiceAdapter


def build_pipeline() -> DiaryPipeline:
    config = load_config()
    storage = InlineDataUrlStorageAdapter()
    speech = ClovaSpeechToTextAdapter(
        config["speech"]["client_id"],
        config["speech"]["client_secret"] or config["speech"]["secret_key"],
    )
    repository = InMemoryDiaryRepository()
    return DiaryPipeline(repository, storage, speech)


# 상태 관리 딕셔너리 (메모리 유지)
pipeline = build_pipeline()
repository = pipeline.repo
diary_states: dict[str, DiaryOrchestrationState] = {}
generation_jobs: dict[str, dict[str, Any]] = {}
generation_tasks: set[asyncio.Task[Any]] = set()
media_jobs: dict[str, dict[str, Any]] = {}
media_tasks: set[asyncio.Task[Any]] = set()

diary_orchestrator = DiaryOrchestrator(
    chat_agent=Hcx005MultimodalChatAgent(load_config()),
    generation_agent=Hcx007DiaryGenerationAgent(load_config()),
)

media_config = load_config()
avatar_config = media_config["avatar"]
avatar_extra_inputs: tuple[Any, ...] = ()
if avatar_config["profile"] == "sadtalker":
    avatar_extra_inputs = (
        "crop",       # preprocess
        True,         # still mode
        False,        # face enhancer
        1,            # batch size
        256,          # face model resolution
        0,            # pose style
        "facevid2vid",
        1.0,          # expression scale
        False,        # use reference video
        None,         # reference video
        "pose",       # reference information
        False,        # idle mode
        5,            # idle video length (unused with audio)
        True,         # eye blink
    )
media_storage_adapter = NcpObjectStorageAdapter(media_config["object_storage"])
diary_media_orchestrator = DiaryMediaOrchestrator(
    script_agent=Hcx007ScriptGenerationAgent(media_config),
    voice_adapter=ClovaVoiceAdapter(media_config),
    storage_adapter=media_storage_adapter,
    avatar_adapter=HuggingFaceSpaceAvatarAdapter(
        source_image=avatar_config["image_path"],
        space_id=avatar_config["space_id"],
        api_name=avatar_config["api_name"],
        token=avatar_config["token"],
        timeout_s=avatar_config["timeout_s"],
        audio_suffix=".mp3",
        extra_inputs=avatar_extra_inputs,
    ),
    config=media_config,
)
diary_deletion_orchestrator = DiaryDeletionOrchestrator(
    storage_adapter=media_storage_adapter,
)


def get_pipeline() -> DiaryPipeline:
    return pipeline


def get_diary_orchestrator() -> DiaryOrchestrator:
    return diary_orchestrator


def get_diary_media_orchestrator() -> DiaryMediaOrchestrator:
    return diary_media_orchestrator


def get_diary_deletion_orchestrator() -> DiaryDeletionOrchestrator:
    return diary_deletion_orchestrator


def get_media_storage_adapter() -> StorageAdapter:
    return media_storage_adapter


# --- 상담 -----------------------------------------------------------------
counsel_knowledge = InMemoryCounselKnowledge()
counsel_ontology = InMemoryPersonalOntology()


async def get_counsel_store(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SQLAlchemyConversationStore:
    """요청 스코프 DB 세션으로 상담 이력 저장소를 만든다.

    인메모리 스텁은 프로세스가 죽으면 대화가 사라지고 워커가 여러 개면
    이력이 갈린다. 서버가 보관하는 단일 이력이라야 안전 규칙 우회도 막힌다.
    """
    return SQLAlchemyConversationStore(db)


async def get_counsel_diary(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SqlDiaryMemory:
    """상담이 참고할 과거 일기 검색기 (H-02).

    상담과 일기가 같은 DB를 보므로 요청 스코프 세션을 그대로 쓴다. 관련도
    임계값은 config에서 온다 — 실측으로 옮기는 값이라 코드에 박지 않는다.
    """
    return SqlDiaryMemory(db, thresholds=DiaryThresholds.from_config(load_config()))


def get_counsel_flow(
    store: Annotated[ConversationStore, Depends(get_counsel_store)],
    diary: Annotated[DiaryMemoryPort, Depends(get_counsel_diary)],
) -> CounselFlow:
    config = load_config()
    return CounselFlow(
        context_agent=ContextAgent(config),
        counselor_agent=CounselorAgent(config),
        knowledge=counsel_knowledge,
        ontology=counsel_ontology,
        store=store,
        diary=diary,
    )
