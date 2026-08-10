import asyncio
from typing import Any

from backend.agents.counsel_chatbot import ContextAgent, CounselorAgent
from backend.agents.diary_chatbot import Hcx005MultimodalChatAgent, Hcx007DiaryGenerationAgent
from backend.config import load_config
from backend.orchestration.diary_orchestrator import DiaryOrchestrationState, DiaryOrchestrator
from backend.orchestration.diary_pipeline import DiaryPipeline
from backend.orchestration.counsel_flow import CounselFlow
from backend.repositories import InMemoryConversationStore, InMemoryDiaryRepository
from backend.services.knowledge import (
    InMemoryCounselKnowledge,
    InMemoryPersonalOntology,
)
from backend.services.speech.clova import ClovaSpeechToTextAdapter
from backend.services.storage.inline import InlineDataUrlStorageAdapter

repository = InMemoryDiaryRepository()


def build_pipeline() -> DiaryPipeline:
    config = load_config()
    storage = InlineDataUrlStorageAdapter()
    speech = ClovaSpeechToTextAdapter(
        config["speech"]["client_id"],
        config["speech"]["client_secret"] or config["speech"]["secret_key"],
    )
    return DiaryPipeline(repository, storage, speech)


pipeline = build_pipeline()
diary_orchestrator = DiaryOrchestrator(
    chat_agent=Hcx005MultimodalChatAgent(load_config()),
    generation_agent=Hcx007DiaryGenerationAgent(load_config()),
)
diary_states: dict[str, DiaryOrchestrationState] = {}
generation_jobs: dict[str, dict[str, Any]] = {}
generation_tasks: set[asyncio.Task[Any]] = set()


def get_pipeline() -> DiaryPipeline:
    return pipeline


def get_diary_orchestrator() -> DiaryOrchestrator:
    return diary_orchestrator


# --- 상담 -----------------------------------------------------------------
#
# 스텁은 상태를 들고 있으므로 요청마다 새로 만들지 않는다. 대화 이력이 매번
# 초기화되고 인덱스도 다시 만들어진다.
#
# 실제 구현이 준비되면 아래 네 개만 바꾼다. 에이전트·흐름 코드는 그대로다.
counsel_store = InMemoryConversationStore()            # TODO: MySQL 저장소
counsel_knowledge = InMemoryCounselKnowledge()         # TODO: 상담 가이드라인 KB
counsel_ontology = InMemoryPersonalOntology()          # TODO: 개인 온톨로지


def get_counsel_flow() -> CounselFlow:
    config = load_config()
    return CounselFlow(
        context_agent=ContextAgent(config),
        counselor_agent=CounselorAgent(config),
        knowledge=counsel_knowledge,
        ontology=counsel_ontology,
        store=counsel_store,
    )
