"""Calendar API integration tests (K-01/K-02)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.agents.diary_chatbot.models import DiaryVersion
from backend.api.schemas import InputType, NormalizedInputItem, ProcessingStatus
from backend.main import app
from backend.repositories.sqlalchemy import SQLAlchemyDiaryRepository
from database.conn.db import get_db
from database.models import (
    AvatarVideo,
    Base,
    DiaryInput,
    DiarySession,
    DiaryVersion as ORMDiaryVersion,
    NarrationScript,
    User,
)


@pytest.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def client(db: AsyncSession) -> AsyncClient:
    async def override_get_db():
        yield db

    # `clear()` 로 끝내면 `test_preprocessing.py` 가 모듈 로드 시점에 걸어 둔
    # 오버라이드까지 지워져, 그쪽 TestClient 가 실 DB 로 떨어진다.
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


async def _seed_calendar_fixtures(db: AsyncSession) -> None:
    user = User(user_id="calendar-user", consent_scope={"history": True})
    db.add(user)

    completed = DiarySession(
        session_id="session-completed",
        user_id="calendar-user",
        diary_date=date(2026, 8, 1),
        status="completed",
        latitude=Decimal("37.5665"),
        longitude=Decimal("126.9780"),
        location_name="Seoul Hall",
    )
    awaiting = DiarySession(
        session_id="session-awaiting",
        user_id="calendar-user",
        diary_date=date(2026, 8, 2),
        status="awaiting_approval",
    )
    same_day = DiarySession(
        session_id="session-same-day",
        user_id="calendar-user",
        diary_date=date(2026, 8, 2),
        status="active",
    )
    db.add_all([completed, awaiting, same_day])

    db.add_all(
        [
            ORMDiaryVersion(
                version_id="version-completed",
                session_id="session-completed",
                title="Happy Day",
                summary="A bright day in Seoul.",
                content="Seoul afternoon was warm and pleasant.",
                paragraphs=["Morning walk", "Afternoon coffee", "Evening rest"],
                evidence_input_ids=["input-text"],
                emotion_tags=["happy"],
                approved=True,
            ),
            ORMDiaryVersion(
                version_id="version-draft",
                session_id="session-awaiting",
                title="Draft Monday",
                summary="Waiting for approval.",
                content="Monday draft body text.",
                emotion_tags=["tired"],
                approved=False,
            ),
        ]
    )

    db.add(
        NarrationScript(
            script_id="narration-completed",
            diary_version_id="version-completed",
            narration_text="Today in Seoul felt warm and bright.",
            status="completed",
            audio_url="https://storage.example/narration.mp3",
        )
    )
    db.add(
        AvatarVideo(
            video_id="video-completed",
            version_id="version-completed",
            status="completed",
            storage_url="https://storage.example/video.mp4",
        )
    )
    db.add(
        DiaryInput(
            input_id="input-text",
            session_id="session-completed",
            type="text",
            transcript="오늘은 정말 화창했다.",
        )
    )
    await db.commit()


@pytest.mark.anyio
async def test_calendar_list_returns_preview_only(client: AsyncClient, db: AsyncSession) -> None:
    await _seed_calendar_fixtures(db)

    response = await client.get(
        "/api/calendar",
        params={
            "user_id": "calendar-user",
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_entries"] == 3
    completed_entry = next(
        item for item in payload["entries"] if item["session_id"] == "session-completed"
    )
    assert completed_entry["title"] == "Happy Day"
    assert "content" not in completed_entry
    assert "diary_inputs" not in completed_entry


@pytest.mark.anyio
async def test_calendar_detail_returns_full_entry(client: AsyncClient, db: AsyncSession) -> None:
    await _seed_calendar_fixtures(db)

    response = await client.get(
        "/api/calendar/session-completed",
        params={"user_id": "calendar-user"},
    )
    assert response.status_code == 200
    detail = response.json()
    assert detail["content"] == "Seoul afternoon was warm and pleasant."
    assert detail["paragraphs"] == ["Morning walk", "Afternoon coffee", "Evening rest"]
    assert detail["evidence_input_ids"] == ["input-text"]
    assert detail["narration_text"] == "Today in Seoul felt warm and bright."
    assert len(detail["diary_inputs"]) == 1
    assert len(detail["versions"]) == 1


@pytest.mark.anyio
async def test_calendar_emotions_endpoint(client: AsyncClient, db: AsyncSession) -> None:
    await _seed_calendar_fixtures(db)

    response = await client.get(
        "/api/calendar/emotions",
        params={"user_id": "calendar-user", "start_date": "2026-08-01", "end_date": "2026-08-10"},
    )
    assert response.status_code == 200
    emotions = response.json()["emotions"]
    assert "happy" in emotions
    assert "tired" in emotions


@pytest.mark.anyio
async def test_calendar_processing_filter_matches_awaiting_approval(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _seed_calendar_fixtures(db)

    response = await client.get(
        "/api/calendar",
        params={
            "user_id": "calendar-user",
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
            "status": "processing",
        },
    )
    assert response.status_code == 200
    session_ids = {item["session_id"] for item in response.json()["entries"]}
    assert session_ids == {"session-awaiting"}


@pytest.mark.anyio
async def test_calendar_supports_multiple_status_filters(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _seed_calendar_fixtures(db)

    response = await client.get(
        "/api/calendar",
        params=[
            ("user_id", "calendar-user"),
            ("start_date", "2026-08-01"),
            ("end_date", "2026-08-10"),
            ("status", "completed"),
            ("status", "active"),
        ],
    )
    assert response.status_code == 200
    session_ids = {item["session_id"] for item in response.json()["entries"]}
    assert session_ids == {"session-completed", "session-same-day"}


@pytest.mark.anyio
async def test_calendar_keyword_search_includes_transcript(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _seed_calendar_fixtures(db)

    response = await client.get(
        "/api/calendar",
        params={
            "user_id": "calendar-user",
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
            "keyword": "화창",
        },
    )
    assert response.status_code == 200
    assert len(response.json()["entries"]) == 1
    assert response.json()["entries"][0]["session_id"] == "session-completed"


@pytest.mark.anyio
async def test_diary_persistence_is_visible_in_calendar(db: AsyncSession) -> None:
    async def override_get_db():
        yield db

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)

    repository = SQLAlchemyDiaryRepository(db)
    await repository.save_session(
        session_id="session-e2e",
        user_id="calendar-e2e-user",
        diary_date=date(2026, 8, 12),
    )
    await repository.save_inputs(
        session_id="session-e2e",
        items=[
            NormalizedInputItem(
                input_id="text-e2e",
                type=InputType.TEXT,
                transcript="캘린더 E2E 테스트 문장입니다.",
                status=ProcessingStatus.OK,
            )
        ],
    )
    await repository.save_version(
        DiaryVersion(
            version_id="version-e2e",
            session_id="session-e2e",
            title="E2E 일기",
            paragraphs=["첫 문단", "둘째 문단", "셋째 문단"],
            summary="E2E 요약",
            content="E2E 본문 내용",
            emotion_tags=["calm"],
            evidence_input_ids=["text-e2e"],
        )
    )
    db.add(
        NarrationScript(
            script_id="narration-e2e",
            diary_version_id="version-e2e",
            narration_text="E2E 나레이션 대본",
            status="completed",
        )
    )
    await db.commit()

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        list_response = await ac.get(
            "/api/calendar",
            params={
                "user_id": "calendar-e2e-user",
                "start_date": "2026-08-12",
                "end_date": "2026-08-12",
            },
        )
        detail_response = await ac.get(
            "/api/calendar/session-e2e",
            params={"user_id": "calendar-e2e-user"},
        )

    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)

    assert list_response.status_code == 200
    assert list_response.json()["summary"]["processing_entries"] == 1
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == "processing"
    assert detail["content"] == "E2E 본문 내용"
    assert detail["narration_text"] == "E2E 나레이션 대본"
