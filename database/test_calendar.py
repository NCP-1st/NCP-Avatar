"""Unit tests for database models and calendar query logic."""

import asyncio
from datetime import date, datetime
from decimal import Decimal
import math
import sys
import os

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.models import Base, User, DiarySession, DiaryVersion, AvatarVideo


async def run_tests():
    print("Initializing test database (SQLite In-Memory)...")
    # Use SQLite in-memory engine with aiosqlite async driver
    TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with engine.begin() as conn:
        # Create all tables defined in models.py
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created successfully!")

    async with AsyncSessionLocal() as session:
        # 1. Insert mock data
        user = User(
            user_id="test_user_1",
            consent_scope={"counsel": True, "history": True},
            avatar_id="avatar_default",
            timezone="Asia/Seoul",
        )
        session.add(user)

        # Day 1: Completed, approved, with completed video, located in Seoul
        s1 = DiarySession(
            session_id="session_1",
            user_id="test_user_1",
            diary_date=date(2026, 8, 1),
            status="completed",
            latitude=Decimal("37.5665"),
            longitude=Decimal("126.9780"),
            location_name="Seoul City Hall",
        )
        session.add(s1)

        v1_draft = DiaryVersion(
            version_id="version_1_1",
            session_id="session_1",
            title="First Draft Title",
            summary="Draft summary",
            script="Draft script",
            emotion_tags=["sad"],
            approved=False,
            created_at=datetime(2026, 8, 1, 20, 0),
        )
        v1_approved = DiaryVersion(
            version_id="version_1_2",
            session_id="session_1",
            title="Happy Day in Seoul",
            summary="Today was a great day visiting Seoul City Hall.",
            script="Seoul was awesome and the weather was great today.",
            emotion_tags=["happy", "excited"],
            approved=True,
            created_at=datetime(2026, 8, 1, 21, 0),
        )
        session.add_all([v1_draft, v1_approved])

        video1 = AvatarVideo(
            video_id="video_1",
            version_id="version_1_2",
            status="completed",
            storage_url="https://s3.ncp.com/videos/v1.mp4",
            duration=30,
        )
        session.add(video1)

        # Day 2: Processing, not approved, only has draft version
        s2 = DiarySession(
            session_id="session_2",
            user_id="test_user_1",
            diary_date=date(2026, 8, 2),
            status="processing",
        )
        session.add(s2)

        v2_draft = DiaryVersion(
            version_id="version_2_1",
            session_id="session_2",
            title="Tired Monday",
            summary="Very tired today after working late.",
            script="Feeling sleepy.",
            emotion_tags=["tired"],
            approved=False,
        )
        session.add(v2_draft)

        # Day 3: Failed, no versions created
        s3 = DiarySession(
            session_id="session_3",
            user_id="test_user_1",
            diary_date=date(2026, 8, 3),
            status="failed",
        )
        session.add(s3)

        # Day 4: Completed, approved, video processing, located in Busan
        s4 = DiarySession(
            session_id="session_4",
            user_id="test_user_1",
            diary_date=date(2026, 8, 4),
            status="completed",
            latitude=Decimal("35.1796"),
            longitude=Decimal("129.0756"),
            location_name="Busan City Hall",
        )
        session.add(s4)

        v4_approved = DiaryVersion(
            version_id="version_4_1",
            session_id="session_4",
            title="Sunny Busan Beach",
            summary="Relaxed at Haeundae beach today.",
            script="The ocean breeze was refreshing.",
            emotion_tags=["calm"],
            approved=True,
        )
        session.add(v4_approved)

        video4 = AvatarVideo(
            video_id="video_4",
            version_id="version_4_1",
            status="processing",
        )
        session.add(video4)

        await session.commit()
        print("Mock data seeded successfully!")

        # Helper to execute test queries
        async def run_query(
            status_filter=None,
            emotion_filter=None,
            keyword_filter=None,
            lat=None,
            lon=None,
            rad=1000.0
        ):
            # Define window ranking subquery
            version_rank_sub = (
                select(
                    DiaryVersion.version_id,
                    DiaryVersion.session_id,
                    DiaryVersion.title,
                    DiaryVersion.summary,
                    DiaryVersion.script,
                    DiaryVersion.emotion_tags,
                    DiaryVersion.approved,
                    func.row_number().over(
                        partition_by=DiaryVersion.session_id,
                        order_by=(DiaryVersion.approved.desc(), DiaryVersion.created_at.desc())
                    ).label("rn")
                )
                .subquery()
            )

            # Main query
            stmt = (
                select(
                    DiarySession,
                    version_rank_sub.c.title,
                    version_rank_sub.c.emotion_tags,
                    AvatarVideo.status.label("video_status"),
                    AvatarVideo.storage_url.label("video_url"),
                )
                .outerjoin(version_rank_sub, and_(
                    DiarySession.session_id == version_rank_sub.c.session_id,
                    version_rank_sub.c.rn == 1
                ))
                .outerjoin(AvatarVideo, version_rank_sub.c.version_id == AvatarVideo.version_id)
                .where(
                    DiarySession.user_id == "test_user_1",
                    DiarySession.diary_date >= date(2026, 8, 1),
                    DiarySession.diary_date <= date(2026, 8, 5),
                )
            )

            if status_filter:
                stmt = stmt.where(DiarySession.status == status_filter)
            if emotion_filter:
                # SQLite fallback check since we are running on SQLite in tests
                stmt = stmt.where(version_rank_sub.c.emotion_tags.like(f'%"{emotion_filter}"%'))
            if keyword_filter:
                keyword_pattern = f"%{keyword_filter}%"
                stmt = stmt.where(
                    or_(
                        version_rank_sub.c.title.ilike(keyword_pattern),
                        version_rank_sub.c.summary.ilike(keyword_pattern),
                        version_rank_sub.c.script.ilike(keyword_pattern),
                    )
                )
            if lat is not None and lon is not None:
                lat_delta = rad / 111000.0
                rad_lat = math.radians(lat)
                cos_lat = math.cos(rad_lat)
                lon_delta = rad / (111000.0 * cos_lat) if cos_lat > 0 else rad / 111000.0

                min_lat = lat - lat_delta
                max_lat = lat + lat_delta
                min_lon = lon - lon_delta
                max_lon = lon + lon_delta

                stmt = stmt.where(
                    DiarySession.latitude.between(min_lat, max_lat),
                    DiarySession.longitude.between(min_lon, max_lon)
                )

            res = await session.execute(stmt)
            return res.all()

        # Test Case 1: Query all range
        rows = await run_query()
        assert len(rows) == 4, f"Expected 4 entries, got {len(rows)}"

        # Test Case 2: Verify fallback to draft title and emotions
        # session_1 has approved version
        row1 = next(r for r in rows if r[0].session_id == "session_1")
        assert row1[1] == "Happy Day in Seoul"
        assert "happy" in row1[2]
        assert row1[3] == "completed"  # video status

        # session_2 has NO approved version, should fallback to latest draft version
        row2 = next(r for r in rows if r[0].session_id == "session_2")
        assert row2[1] == "Tired Monday"
        assert "tired" in row2[2]

        # session_3 has no versions
        row3 = next(r for r in rows if r[0].session_id == "session_3")
        assert row3[1] is None
        assert row3[2] is None

        # Test Case 3: Filter by status
        completed_rows = await run_query(status_filter="completed")
        assert len(completed_rows) == 2, f"Expected 2 completed entries, got {len(completed_rows)}"
        assert {r[0].session_id for r in completed_rows} == {"session_1", "session_4"}

        # Test Case 4: Filter by emotion
        happy_rows = await run_query(emotion_filter="happy")
        assert len(happy_rows) == 1
        assert happy_rows[0][0].session_id == "session_1"

        # Test Case 5: Filter by keyword
        tired_rows = await run_query(keyword_filter="Tired")
        assert len(tired_rows) == 1
        assert tired_rows[0][0].session_id == "session_2"

        # Test Case 6: Filter by location proximity (Seoul, radius 10km)
        # Seoul Hall is at (37.5665, 126.9780)
        seoul_proximity_rows = await run_query(lat=37.5665, lon=126.9780, rad=10000.0)
        assert len(seoul_proximity_rows) == 1
        assert seoul_proximity_rows[0][0].session_id == "session_1"

        # Busan Hall is at (35.1796, 129.0756), should not show in Seoul 50km query
        seoul_50km_rows = await run_query(lat=37.5665, lon=126.9780, rad=50000.0)
        assert len(seoul_50km_rows) == 1
        assert seoul_50km_rows[0][0].session_id == "session_1"

        # Busan proximity query
        busan_rows = await run_query(lat=35.1796, lon=129.0756, rad=10000.0)
        assert len(busan_rows) == 1
        assert busan_rows[0][0].session_id == "session_4"

        print("All database and query validation unit tests PASSED successfully!")


if __name__ == "__main__":
    asyncio.run(run_tests())
