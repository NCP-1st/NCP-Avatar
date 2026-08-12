"""Seed local SQLite data for calendar UI/API manual testing.

Usage:
    DATABASE_URL=sqlite+aiosqlite:///./data/mediary_local.db python database/seed_local_demo.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.models import (
    AvatarVideo,
    Base,
    DiaryInput,
    DiarySession,
    DiaryVersion,
    NarrationScript,
    User,
)

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./data/mediary_local.db"
DEMO_USER_ID = "streamlit-test-user"


async def seed() -> None:
    database_url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    os.makedirs("data", exist_ok=True)

    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add(
            User(
                user_id=DEMO_USER_ID,
                consent_scope={"history": True, "counsel": True},
                avatar_id="avatar_default",
            )
        )

        completed = DiarySession(
            session_id="demo-session-completed",
            user_id=DEMO_USER_ID,
            diary_date=date(2026, 8, 10),
            status="completed",
            latitude=Decimal("37.5665"),
            longitude=Decimal("126.9780"),
            location_name="서울시청",
        )
        awaiting = DiarySession(
            session_id="demo-session-awaiting",
            user_id=DEMO_USER_ID,
            diary_date=date(2026, 8, 12),
            status="awaiting_approval",
        )
        failed = DiarySession(
            session_id="demo-session-failed",
            user_id=DEMO_USER_ID,
            diary_date=date(2026, 8, 8),
            status="failed",
        )
        session.add_all([completed, awaiting, failed])

        session.add_all(
            [
                DiaryVersion(
                    version_id="demo-version-completed",
                    session_id="demo-session-completed",
                    title="화창한 서울 하루",
                    summary="서울시청 앞에서 즐거운 산책을 했다.",
                    content="오늘은 날씨가 정말 좋아서 서울시청 주변을 천천히 걸었다.",
                    emotion_tags=["happy", "calm"],
                    approved=True,
                    created_at=datetime(2026, 8, 10, 21, 0),
                ),
                DiaryVersion(
                    version_id="demo-version-awaiting",
                    session_id="demo-session-awaiting",
                    title="오늘의 초안",
                    summary="아직 승인 전인 오늘 일기 초안이다.",
                    content="오늘은 팀 미팅 후 캘린더 기능을 로컬에서 테스트했다.",
                    emotion_tags=["excited"],
                    approved=False,
                    created_at=datetime(2026, 8, 12, 18, 30),
                ),
            ]
        )

        session.add_all(
            [
                NarrationScript(
                    script_id="demo-narration-completed",
                    diary_version_id="demo-version-completed",
                    narration_text="서울의 따뜻한 햇살 아래, 오늘 하루도 충분히 좋았습니다.",
                    status="completed",
                    audio_url="https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
                ),
                DiaryInput(
                    input_id="demo-input-text",
                    session_id="demo-session-completed",
                    type="text",
                    transcript="오늘은 정말 화창했다.",
                ),
                DiaryInput(
                    input_id="demo-input-image",
                    session_id="demo-session-completed",
                    type="image",
                    storage_url="https://picsum.photos/seed/mediary/800/600",
                    transcript="서울시청 앞 풍경",
                ),
                AvatarVideo(
                    video_id="demo-video-completed",
                    version_id="demo-version-completed",
                    status="completed",
                    storage_url="https://samplelib.com/lib/preview/mp4/sample-5s.mp4",
                    duration=30,
                ),
            ]
        )
        await session.commit()

    await engine.dispose()
    print(f"Seeded demo calendar data for user_id={DEMO_USER_ID!r}")
    print("Sample dates: 2026-08-08 (failed), 2026-08-10 (completed), 2026-08-12 (processing)")


if __name__ == "__main__":
    asyncio.run(seed())
