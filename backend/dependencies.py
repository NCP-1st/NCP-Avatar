import asyncio
from typing import Any

from backend.agents.counsel_chatbot import ContextAgent, CounselorAgent
from backend.agents.diary_chatbot import Hcx005MultimodalChatAgent, Hcx007DiaryGenerationAgent
from backend.config import load_config
from backend.orchestration.counsel_flow import CounselFlow
from backend.orchestration.diary_orchestrator import DiaryOrchestrationState, DiaryOrchestrator
from backend.orchestration.diary_pipeline import DiaryPipeline
from backend.repositories import InMemoryConversationStore, InMemoryDiaryRepository
from backend.services.knowledge import (
    InMemoryCounselKnowledge,
    InMemoryPersonalOntology,
)
from backend.services.speech.clova import ClovaSpeechToTextAdapter
from backend.services.storage.inline import InlineDataUrlStorageAdapter
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

diary_orchestrator = DiaryOrchestrator(
    chat_agent=Hcx005MultimodalChatAgent(load_config()),
    generation_agent=Hcx007DiaryGenerationAgent(load_config()),
)


def get_pipeline() -> DiaryPipeline:
    return pipeline


def get_diary_orchestrator() -> DiaryOrchestrator:
    return diary_orchestrator


# --- 상담 -----------------------------------------------------------------
counsel_store = InMemoryConversationStore()
counsel_knowledge = InMemoryCounselKnowledge()
counsel_ontology = InMemoryPersonalOntology()


def get_counsel_flow() -> CounselFlow:
    config = load_config()
    return CounselFlow(
        context_agent=ContextAgent(config),
        counselor_agent=CounselorAgent(config),
        knowledge=counsel_knowledge,
        ontology=counsel_ontology,
        store=counsel_store,
    )
