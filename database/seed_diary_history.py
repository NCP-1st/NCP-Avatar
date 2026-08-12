"""Seed approved diary history from an editable JSON fixture.

This script never drops tables or removes existing rows. It uses deterministic
mock IDs, so running it again updates only the same fixture-owned sessions and
versions.

Usage:
    python -m database.seed_diary_history --dry-run
    python -m database.seed_diary_history
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import select

from database.conn.db import AsyncSessionLocal, engine
from database.models import DiarySession, DiaryVersion, NarrationScript, User

DEFAULT_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "diary_history_2026_08_11.json"
)


class FixtureDiary(BaseModel):
    diary_date: date
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1)
    content: str = Field(min_length=1)
    narration_text: str | None = Field(default=None, min_length=10, max_length=200)
    emotion_tags: list[str] = Field(default_factory=list)
    created_at: datetime


class DiaryHistoryFixture(BaseModel):
    user_id: str = Field(min_length=1, max_length=50)
    period: dict[str, date]
    diaries: list[FixtureDiary] = Field(min_length=1)


def load_fixture(path: Path) -> DiaryHistoryFixture:
    fixture = DiaryHistoryFixture.model_validate_json(path.read_text(encoding="utf-8"))
    dates = [item.diary_date for item in fixture.diaries]
    if len(dates) != len(set(dates)):
        raise ValueError("fixture contains duplicate diary_date values")
    if dates != sorted(dates):
        raise ValueError("fixture diaries must be ordered by diary_date")
    if len(dates) != 30:
        raise ValueError("fixture must contain exactly 30 diary entries")
    expected_dates = [dates[0] + timedelta(days=offset) for offset in range(30)]
    if dates != expected_dates:
        raise ValueError("fixture diary dates must be 30 consecutive calendar days")
    if dates[0] != fixture.period.get("start_date"):
        raise ValueError("period.start_date does not match the first diary")
    if dates[-1] != fixture.period.get("end_date"):
        raise ValueError("period.end_date does not match the last diary")
    return fixture


def fixture_ids(diary_date: date) -> tuple[str, str, str]:
    suffix = diary_date.strftime("%Y%m%d")
    return (
        f"mock-session-{suffix}",
        f"mock-version-{suffix}",
        f"mock-narration-{suffix}",
    )


async def seed_fixture(fixture: DiaryHistoryFixture) -> dict[str, int]:
    counts = {
        "sessions_created": 0,
        "sessions_reused": 0,
        "versions_created": 0,
        "versions_updated": 0,
        "narrations_created": 0,
        "narrations_updated": 0,
        "existing_diaries_preserved": 0,
    }
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await db.get(User, fixture.user_id)
            if user is None:
                raise LookupError(
                    f"user_id={fixture.user_id!r} does not exist; create the user first"
                )

            for item in fixture.diaries:
                session_id, version_id, script_id = fixture_ids(item.diary_date)
                narration_text = item.narration_text or item.summary
                stored_session = await db.scalar(
                    select(DiarySession).where(
                        DiarySession.user_id == fixture.user_id,
                        DiarySession.diary_date == item.diary_date,
                    )
                )
                if stored_session is None:
                    stored_session = DiarySession(
                        session_id=session_id,
                        user_id=fixture.user_id,
                        diary_date=item.diary_date,
                        status="completed",
                        created_at=item.created_at,
                        updated_at=item.created_at,
                    )
                    db.add(stored_session)
                    counts["sessions_created"] += 1
                else:
                    session_id = stored_session.session_id
                    counts["sessions_reused"] += 1

                approved_version = await db.scalar(
                    select(DiaryVersion)
                    .where(
                        DiaryVersion.session_id == session_id,
                        DiaryVersion.approved.is_(True),
                    )
                    .order_by(DiaryVersion.created_at.desc())
                    .limit(1)
                )
                if (
                    approved_version is not None
                    and approved_version.version_id != version_id
                ):
                    counts["existing_diaries_preserved"] += 1
                    continue

                stored_session.status = "completed"

                stored_version = await db.get(DiaryVersion, version_id)
                if stored_version is None:
                    db.add(
                        DiaryVersion(
                            version_id=version_id,
                            session_id=session_id,
                            title=item.title,
                            summary=item.summary,
                            content=item.content,
                            emotion_tags=item.emotion_tags,
                            approved=True,
                            created_at=item.created_at,
                        )
                    )
                    counts["versions_created"] += 1
                else:
                    if stored_version.session_id != session_id:
                        raise ValueError(
                            f"version_id={version_id!r} belongs to another session"
                        )
                    stored_version.title = item.title
                    stored_version.summary = item.summary
                    stored_version.content = item.content
                    stored_version.emotion_tags = item.emotion_tags
                    stored_version.approved = True
                    stored_version.created_at = item.created_at
                    counts["versions_updated"] += 1

                stored_narration = await db.scalar(
                    select(NarrationScript).where(
                        NarrationScript.diary_version_id == version_id
                    )
                )
                narration_emotion = (
                    item.emotion_tags[0] if item.emotion_tags else None
                )
                if stored_narration is None:
                    db.add(
                        NarrationScript(
                            script_id=script_id,
                            diary_version_id=version_id,
                            narration_text=narration_text,
                            emotion=narration_emotion,
                            tone="따뜻한 회상",
                            target_duration_seconds=12,
                            status="completed",
                            llm_model="mock-fixture",
                            created_at=item.created_at,
                            updated_at=item.created_at,
                        )
                    )
                    counts["narrations_created"] += 1
                else:
                    stored_narration.narration_text = narration_text
                    stored_narration.emotion = narration_emotion
                    stored_narration.tone = "따뜻한 회상"
                    stored_narration.target_duration_seconds = 12
                    stored_narration.status = "completed"
                    stored_narration.llm_model = "mock-fixture"
                    stored_narration.error_code = None
                    stored_narration.created_at = item.created_at
                    stored_narration.updated_at = item.created_at
                    counts["narrations_updated"] += 1

    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE_PATH,
        help="Path to the diary history JSON fixture",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and summarize the fixture without connecting to the database",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    fixture = load_fixture(args.fixture.resolve())
    print(
        f"Validated {len(fixture.diaries)} diaries for {fixture.user_id!r}: "
        f"{fixture.diaries[0].diary_date} through {fixture.diaries[-1].diary_date}"
    )
    if args.dry_run:
        return

    try:
        counts = await seed_fixture(fixture)
    finally:
        await engine.dispose()
    print(
        "Seed complete: "
        f"{counts['sessions_created']} sessions created, "
        f"{counts['sessions_reused']} sessions reused, "
        f"{counts['versions_created']} versions created, "
        f"{counts['versions_updated']} versions updated, "
        f"{counts['narrations_created']} narrations created, "
        f"{counts['narrations_updated']} narrations updated, "
        f"{counts['existing_diaries_preserved']} existing approved diaries preserved"
    )


if __name__ == "__main__":
    asyncio.run(main())
