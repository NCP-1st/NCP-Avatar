"""Map diary API integration tests (L-01)."""

from __future__ import annotations

from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.main import app
from database.conn.db import get_db
from database.models import Base, DiarySession, DiaryVersion, LocationMessage, User


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

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


async def _seed_map_diaries(db: AsyncSession) -> None:
    db.add_all(
        [
            User(user_id="map-user", consent_scope={"history": True}),
            User(user_id="other-user", consent_scope={"history": True}),
        ]
    )
    db.add_all(
        [
            DiarySession(
                session_id="map-session-located",
                user_id="map-user",
                diary_date=date(2026, 8, 10),
                status="completed",
            ),
            DiarySession(
                session_id="map-session-unlocated",
                user_id="map-user",
                diary_date=date(2026, 8, 11),
                status="completed",
            ),
            DiarySession(
                session_id="map-session-draft",
                user_id="map-user",
                diary_date=date(2026, 8, 12),
                status="awaiting_approval",
            ),
            DiarySession(
                session_id="map-session-other",
                user_id="other-user",
                diary_date=date(2026, 8, 12),
                status="completed",
            ),
        ]
    )
    db.add_all(
        [
            DiaryVersion(
                version_id="map-version-located",
                session_id="map-session-located",
                title="서울 산책",
                summary="서울을 걸었다.",
                content="맑은 날 서울을 천천히 걸었다.",
                emotion_tags=["평온"],
                approved=True,
            ),
            DiaryVersion(
                version_id="map-version-unlocated",
                session_id="map-session-unlocated",
                title="바닷가 여행",
                summary="바다를 보았다.",
                content="파도 소리를 들으며 쉬었다.",
                emotion_tags=["행복"],
                approved=True,
            ),
            DiaryVersion(
                version_id="map-version-draft",
                session_id="map-session-draft",
                title="승인 전 일기",
                summary="초안이다.",
                content="아직 승인하지 않았다.",
                approved=False,
            ),
            DiaryVersion(
                version_id="map-version-other",
                session_id="map-session-other",
                title="다른 사용자 일기",
                summary="소유자가 다르다.",
                content="접근할 수 없어야 한다.",
                approved=True,
            ),
        ]
    )
    db.add(
        LocationMessage(
            map_id="map-existing",
            user_id="map-user",
            session_id="map-session-located",
            version_id="map-version-located",
            latitude=37.5665,
            longitude=126.9780,
        )
    )
    await db.commit()


@pytest.mark.anyio
async def test_map_list_returns_only_owned_approved_diaries(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed_map_diaries(db)

    response = await client.get(
        "/api/maps/diaries",
        params={"user_id": "map-user", "location_status": "all"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert {item["version_id"] for item in payload} == {
        "map-version-located",
        "map-version-unlocated",
    }
    located = next(item for item in payload if item["is_located"])
    assert located["map_id"] == "map-existing"
    assert located["latitude"] == pytest.approx(37.5665)


@pytest.mark.anyio
async def test_map_list_filters_location_and_title(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed_map_diaries(db)

    located = await client.get(
        "/api/maps/diaries",
        params={"user_id": "map-user", "location_status": "located"},
    )
    unlocated_search = await client.get(
        "/api/maps/diaries",
        params={
            "user_id": "map-user",
            "location_status": "unlocated",
            "keyword": "바닷가",
        },
    )

    assert [item["version_id"] for item in located.json()] == [
        "map-version-located"
    ]
    assert [item["version_id"] for item in unlocated_search.json()] == [
        "map-version-unlocated"
    ]


@pytest.mark.anyio
async def test_create_location_and_reject_duplicate(
    client: AsyncClient, db: AsyncSession
) -> None:
    await _seed_map_diaries(db)
    request = {
        "user_id": "map-user",
        "version_id": "map-version-unlocated",
        "latitude": 35.1796,
        "longitude": 129.0756,
    }

    created = await client.post("/api/maps/diaries", json=request)
    duplicate = await client.post("/api/maps/diaries", json=request)

    assert created.status_code == 201
    assert created.json()["is_located"] is True
    assert created.json()["session_id"] == "map-session-unlocated"
    assert duplicate.status_code == 409


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("user_id", "version_id"),
    [
        ("map-user", "map-version-draft"),
        ("map-user", "map-version-other"),
    ],
)
async def test_create_location_rejects_unapproved_or_unowned_version(
    client: AsyncClient,
    db: AsyncSession,
    user_id: str,
    version_id: str,
) -> None:
    await _seed_map_diaries(db)

    response = await client.post(
        "/api/maps/diaries",
        json={
            "user_id": user_id,
            "version_id": version_id,
            "latitude": 37.5,
            "longitude": 127.0,
        },
    )

    assert response.status_code == 404
