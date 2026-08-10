import asyncio
from typing import Any

from backend.agents.diary_chatbot import Hcx005MultimodalChatAgent, Hcx007DiaryGenerationAgent
from backend.config import load_config
from backend.orchestration.diary_orchestrator import DiaryOrchestrationState, DiaryOrchestrator
from backend.orchestration.diary_pipeline import DiaryPipeline
from backend.repositories import InMemoryDiaryRepository
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
