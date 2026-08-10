import asyncio
from typing import Any

from backend.agents.diary_chatbot import Hcx005MultimodalChatAgent, Hcx007DiaryGenerationAgent
from backend.config import get_settings, load_config
from backend.orchestration.diary_orchestrator import DiaryOrchestrationState, DiaryOrchestrator
from backend.orchestration.diary_pipeline import DiaryPipeline
from backend.repositories import InMemoryDiaryRepository
from backend.services.speech.clova import ClovaSpeechToTextAdapter
from backend.services.speech.dummy import DummySpeechToTextAdapter
from backend.services.storage.inline import InlineDataUrlStorageAdapter

repository = InMemoryDiaryRepository()


def build_pipeline() -> DiaryPipeline:
    settings = get_settings()
    storage = InlineDataUrlStorageAdapter()
    if settings.use_clova:
        settings.validate_clova()
        speech = ClovaSpeechToTextAdapter(
            settings.clova_speech_client_id or "", settings.clova_speech_client_secret or ""
        )
    else:
        speech = DummySpeechToTextAdapter()
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
