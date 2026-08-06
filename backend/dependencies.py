from backend.config import get_settings
from backend.orchestration.diary_pipeline import DiaryPipeline
from backend.services.speech.clova import ClovaSpeechToTextAdapter
from backend.services.speech.dummy import DummySpeechToTextAdapter
from backend.services.storage.dummy import DummyStorageAdapter
from backend.testing.repository import InMemoryRepository

repository = InMemoryRepository()


def build_pipeline() -> DiaryPipeline:
    settings = get_settings()
    storage = DummyStorageAdapter()
    if settings.use_clova:
        settings.validate_clova()
        speech = ClovaSpeechToTextAdapter(
            settings.clova_speech_client_id or "", settings.clova_speech_client_secret or ""
        )
    else:
        speech = DummySpeechToTextAdapter()
    return DiaryPipeline(repository, storage, speech)


pipeline = build_pipeline()


def get_pipeline() -> DiaryPipeline:
    return pipeline
