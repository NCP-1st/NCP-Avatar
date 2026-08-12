import base64
import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.dependencies import pipeline, repository
from backend.main import app
from backend.services.speech import SpeechToTextAdapter
from database.conn.db import get_db
from database.models import Base


class TestSpeechAdapter(SpeechToTextAdapter):
    async def transcribe(
        self, audio: bytes, *, mime_type: str
    ) -> tuple[str, dict[str, str | float]]:
        return "테스트 음성 인식 결과", {"provider": "test-stt", "confidence": 1.0}


pipeline.stt = TestSpeechAdapter()

test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    poolclass=StaticPool,
)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


async def _create_test_schema() -> None:
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


asyncio.run(_create_test_schema())


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def setup_function() -> None:
    repository.clear()


def create_session() -> str:
    response = client.post("/diary/sessions", json={"user_id": "test-user", "diary_date": "2026-08-06"})
    assert response.status_code == 201
    return response.json()["session_id"]


def test_same_day_reuses_the_diary_session() -> None:
    first = create_session()
    second = create_session()
    assert first == second


def test_session_is_restored_from_db_after_memory_cache_is_cleared() -> None:
    session_id = create_session()
    repository.sessions.pop(session_id, None)

    response = client.get(f"/diary/{session_id}/versions")

    assert response.status_code == 200
    assert response.json()["session_id"] == session_id
    assert session_id in repository.sessions


def test_health_and_multimodal_preprocessing() -> None:
    assert client.get("/health").json() == {"status": "ok"}
    session_id = create_session()
    image = base64.b64encode(b"\x89PNG\r\n\x1a\nplaceholder").decode()
    audio = base64.b64encode(b"test-audio").decode()
    response = client.post(f"/diary/{session_id}/inputs", json={"items": [
        {"input_id": "text-1", "type": "text", "text": "친구와 공원에서 산책했다."},
        {"input_id": "photo-1", "type": "photo", "file_base64": image, "mime_type": "image/png"},
        {"input_id": "audio-1", "type": "audio", "file_base64": audio, "mime_type": "audio/wav"},
    ]})
    assert response.status_code == 200
    assert response.json()["error_count"] == 0
    assert all(item["status"] == "ok" for item in response.json()["items"])
    audio_item = next(item for item in response.json()["items"] if item["type"] == "audio")
    assert audio_item["transcript"] == "테스트 음성 인식 결과"
    assert audio_item["transcript_confirmed"] is False

    confirmed = client.put(
        f"/diary/{session_id}/inputs/audio-1/transcript",
        json={"transcript": "친구와 공원에서 산책해서 즐거웠어"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["transcript_confirmed"] is True
    stored_audio = next(item for item in repository.inputs[session_id] if item.input_id == "audio-1")
    assert stored_audio.transcript == "친구와 공원에서 산책해서 즐거웠어"
    assert stored_audio.transcript_confirmed is True


def test_failed_item_can_be_retried_individually() -> None:
    session_id = create_session()
    invalid = base64.b64encode(b"not-an-image").decode()
    failed = client.post(f"/diary/{session_id}/inputs", json={"items": [
        {"input_id": "text-ok", "type": "text", "text": "정상 텍스트"},
        {"input_id": "photo-retry", "type": "photo", "file_base64": invalid},
    ]})
    body = failed.json()
    assert body["error_count"] == 1
    assert [item["status"] for item in body["items"]] == ["ok", "failed"]
    assert body["items"][1]["error_reason"]

    media = base64.b64encode(b"\x89PNG\r\n\x1a\nvalid-image-placeholder").decode()
    retried = client.post(f"/diary/{session_id}/inputs", json={"items": [{
        "input_id": "photo-retry", "type": "photo", "file_base64": media, "mime_type": "image/png"
    }]})
    assert retried.json()["items"][0]["status"] == "ok"
    assert len(repository.inputs[session_id]) == 2


def test_unconfirmed_audio_is_blocked_before_chat_agent_call() -> None:
    session_id = create_session()
    audio = base64.b64encode(b"test-audio").decode()
    uploaded = client.post(f"/diary/{session_id}/inputs", json={"items": [{
        "input_id": "audio-unconfirmed",
        "type": "audio",
        "file_base64": audio,
        "mime_type": "audio/wav",
    }]})
    assert uploaded.status_code == 200

    response = client.post(
        f"/diary/{session_id}/chat",
        json={"message": "", "input_ids": ["audio-unconfirmed"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "음성 메모의 인식 결과를 먼저 확인해 주세요."


def test_openapi_exposes_only_current_scope() -> None:
    paths = set(client.get("/openapi.json").json()["paths"])
    assert paths == {
        "/health",
        "/diary/sessions",
        "/diary/{session_id}/inputs",
        "/diary/{session_id}/inputs/{input_id}/transcript",
        "/diary/{session_id}/chat",
        "/diary/{session_id}/generate",
        "/diary/{session_id}/versions",
        "/diary/{session_id}/versions/new-chat",
        "/diary/{session_id}/versions/{version_id}/approve",
        "/diary/{session_id}/versions/{version_id}/video",
        "/diary/{session_id}/versions/{version_id}",
        "/diary/{session_id}/review",
        "/diary/jobs/{job_id}",
        "/",
        "/api/calendar",
        "/api/counsel/chat",
        "/api/maps/diaries",
        "/api/script/ai_script",
    }
