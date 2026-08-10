"""Integration tests for Mediary FastAPI calendar endpoints."""

import asyncio
from datetime import date
import sys
import os

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.main import app
from database.conn.db import get_db
from database.models import Base, User, DiaryInput, DiarySession, DiaryVersion, AvatarVideo
from decimal import Decimal


async def run_integration_tests():
    print("Initializing test database for FastAPI app integration test...")
    # Use an in-memory database for testing
    TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Test tables created.")

    # Override get_db dependency in FastAPI app
    async def override_get_db():
        async with AsyncSessionLocal() as session:
            try:
                yield session
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed mock data
    async with AsyncSessionLocal() as session:
        user = User(
            user_id="user_123",
            consent_scope={"history": True},
            avatar_id="avatar_1",
        )
        session.add(user)

        # Session 1: completed, approved
        s1 = DiarySession(
            session_id="session_1",
            user_id="user_123",
            diary_date=date(2026, 8, 6),
            status="completed",
            latitude=Decimal("37.5665"),
            longitude=Decimal("126.9780"),
            location_name="Seoul Hall",
        )
        session.add(s1)

        v1 = DiaryVersion(
            version_id="version_1",
            session_id="session_1",
            title="Sunny Thursday",
            summary="A bright and sunny day.",
            content="Thursday afternoon was nice.",
            emotion_tags=["happy", "calm"],
            approved=True,
        )
        session.add(v1)

        video1 = AvatarVideo(
            video_id="video_1",
            version_id="version_1",
            status="completed",
            storage_url="https://s3.ncp.com/video1.mp4",
        )
        session.add(video1)

        image_input = DiaryInput(
            input_id="input_1",
            session_id="session_1",
            type="image",
            storage_url="https://s3.ncp.com/input/image1.png",
            transcript="서울 시청 앞 풍경 사진",
        )
        text_input = DiaryInput(
            input_id="input_2",
            session_id="session_1",
            type="text",
            storage_url="https://s3.ncp.com/input/text1.txt",
            transcript="오늘은 정말 화창했다.",
        )
        session.add_all([image_input, text_input])
        await session.commit()
        print("Mock data seeded.")

    # Run client requests
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Test health check
        print("Testing root health check endpoint...")
        response = await ac.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        print("Health check response:", data)

        # 2. Test calendar query
        print("Testing GET /api/calendar endpoint...")
        response = await ac.get(
            "/api/calendar",
            params={
                "user_id": "user_123",
                "start_date": "2026-08-01",
                "end_date": "2026-08-10",
            }
        )
        assert response.status_code == 200
        calendar_data = response.json()
        assert calendar_data["user_id"] == "user_123"
        assert len(calendar_data["entries"]) == 1
        assert calendar_data["summary"]["total_entries"] == 1
        assert calendar_data["summary"]["completed_entries"] == 1
        assert calendar_data["summary"]["approved_entries"] == 1

        entry = calendar_data["entries"][0]
        assert entry["session_id"] == "session_1"
        assert entry["diary_date"] == "2026-08-06"
        assert entry["status"] == "completed"
        assert entry["title"] == "Sunny Thursday"
        assert entry["summary"] == "A bright and sunny day."
        assert entry["script"] == "Thursday afternoon was nice."
        assert entry["approved"] is True
        assert "happy" in entry["emotion_tags"]
        assert entry["video_status"] == "completed"
        assert entry["video_url"] == "https://s3.ncp.com/video1.mp4"
        assert entry["location_name"] == "Seoul Hall"
        assert len(entry["diary_inputs"]) == 2
        assert entry["diary_inputs"][0]["type"] == "image"
        assert entry["versions"][0]["version_id"] == "version_1"
        print("Calendar response entry:", entry)

        # 3. Test calendar query with emotion filter
        print("Testing GET /api/calendar with emotion filter...")
        response = await ac.get(
            "/api/calendar",
            params={
                "user_id": "user_123",
                "start_date": "2026-08-01",
                "end_date": "2026-08-10",
                "emotion": "happy",
            }
        )
        assert response.status_code == 200
        assert len(response.json()["entries"]) == 1

        # Test non-matching emotion filter
        response = await ac.get(
            "/api/calendar",
            params={
                "user_id": "user_123",
                "start_date": "2026-08-01",
                "end_date": "2026-08-10",
                "emotion": "sad",
            }
        )
        assert response.status_code == 200
        assert len(response.json()["entries"]) == 0

        # 4. Test calendar query with keyword filter
        print("Testing GET /api/calendar with keyword filter...")
        response = await ac.get(
            "/api/calendar",
            params={
                "user_id": "user_123",
                "start_date": "2026-08-01",
                "end_date": "2026-08-10",
                "keyword": "Sunny",
            }
        )
        assert response.status_code == 200
        assert len(response.json()["entries"]) == 1

        # 5. Test calendar query with location proximity filter
        print("Testing GET /api/calendar with location proximity filter...")
        # Seoul Hall is at (37.5665, 126.9780)
        response = await ac.get(
            "/api/calendar",
            params={
                "user_id": "user_123",
                "start_date": "2026-08-01",
                "end_date": "2026-08-10",
                "latitude": 37.5665,
                "longitude": 126.9780,
                "radius": 5000,
            }
        )
        assert response.status_code == 200
        assert len(response.json()["entries"]) == 1

        # Query far away
        response = await ac.get(
            "/api/calendar",
            params={
                "user_id": "user_123",
                "start_date": "2026-08-01",
                "end_date": "2026-08-10",
                "latitude": 35.1796,  # Busan latitude
                "longitude": 129.0756,
                "radius": 5000,
            }
        )
        assert response.status_code == 200
        assert len(response.json()["entries"]) == 0

        # 6. Test invalid location filter payload
        response = await ac.get(
            "/api/calendar",
            params={
                "user_id": "user_123",
                "start_date": "2026-08-01",
                "end_date": "2026-08-10",
                "latitude": 37.5665,
            }
        )
        assert response.status_code == 400
        assert "provided together" in response.json()["detail"]

    print("All FastAPI integration tests PASSED successfully!")


if __name__ == "__main__":
    asyncio.run(run_integration_tests())
