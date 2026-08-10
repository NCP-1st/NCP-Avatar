from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.agents.diary_chatbot.models import DiaryVersion
from backend.api.schemas import InputType, NormalizedInputItem, ProcessingStatus
from backend.repositories.sqlalchemy import SQLAlchemyDiaryRepository
from database.models import Base, DiaryInput, DiarySession
from database.models import DiaryVersion as ORMDiaryVersion


@pytest.mark.anyio
async def test_diary_workflow_is_persisted() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool
    )
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        repository = SQLAlchemyDiaryRepository(db)
        await repository.save_session(
            session_id="session-db-test",
            user_id="user-db-test",
            diary_date=date(2026, 8, 10),
        )
        await repository.save_inputs(
            session_id="session-db-test",
            items=[
                NormalizedInputItem(
                    input_id="text-db-test",
                    type=InputType.TEXT,
                    transcript="친구와 성수동에서 즐겁게 산책했다.",
                    status=ProcessingStatus.OK,
                )
            ],
        )
        await repository.save_version(
            DiaryVersion(
                version_id="version-db-test",
                session_id="session-db-test",
                title="친구와 산책",
                paragraphs=["친구와 성수동을 걸었다.", "함께여서 즐거웠다.", "좋은 하루였다."],
                summary="친구와 성수동에서 즐겁게 산책한 날",
                content="친구와 성수동을 걸었다. 함께여서 즐거웠다. 좋은 하루였다.",
                emotion_tags=["즐거움"],
                evidence_input_ids=["text-db-test"],
            )
        )

        stored_session = await db.get(DiarySession, "session-db-test")
        stored_input = await db.get(DiaryInput, "text-db-test")
        stored_version = await db.get(ORMDiaryVersion, "version-db-test")

        assert stored_session is not None and stored_session.status == "completed"
        assert stored_input is not None and stored_input.transcript.startswith("친구와")
        assert stored_version is not None
        assert stored_version.content == "친구와 성수동을 걸었다. 함께여서 즐거웠다. 좋은 하루였다."

    await engine.dispose()
