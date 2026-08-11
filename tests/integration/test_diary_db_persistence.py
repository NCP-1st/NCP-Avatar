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
                ),
                NormalizedInputItem(
                    input_id="photo-db-test",
                    type=InputType.PHOTO,
                    storage_url="data:image/jpeg;base64," + "A" * 1000,
                    status=ProcessingStatus.OK,
                ),
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
        stored_photo = await db.get(DiaryInput, "photo-db-test")
        stored_version = await db.get(ORMDiaryVersion, "version-db-test")

        assert stored_session is not None and stored_session.status == "awaiting_approval"
        assert stored_input is not None and stored_input.transcript.startswith("친구와")
        assert stored_photo is not None and stored_photo.storage_url is None
        assert stored_version is not None
        assert stored_version.content == "친구와 성수동을 걸었다. 함께여서 즐거웠다. 좋은 하루였다."

        base_version = await repository.get_version("version-db-test")
        assert base_version is not None
        await repository.save_version(
            base_version.model_copy(update={"version_id": "version-db-test-2"})
        )
        await repository.save_version(
            base_version.model_copy(update={"version_id": "version-db-test-3"})
        )
        with pytest.raises(ValueError, match="최대 3개"):
            await repository.save_version(
                base_version.model_copy(update={"version_id": "version-db-test-4"})
            )
        await db.rollback()

        selected = await repository.finalize_session_versions(
            session_id="session-db-test",
            approved_version_id="version-db-test-2",
        )
        versions = await repository.get_versions("session-db-test")
        assert selected.approved is True
        assert [item.version_id for item in versions if item.approved] == [
            "version-db-test-2"
        ]
        changed = await repository.finalize_session_versions(
            session_id="session-db-test",
            approved_version_id="version-db-test-3",
        )
        assert changed.approved is True
        versions = await repository.get_versions("session-db-test")
        assert [item.version_id for item in versions if item.approved] == [
            "version-db-test-3"
        ]

        await repository.delete_version(
            session_id="session-db-test",
            version_id="version-db-test-3",
        )
        versions = await repository.get_versions("session-db-test")
        assert len(versions) == 2
        assert not any(item.approved for item in versions)
        await db.refresh(stored_session)
        assert stored_session.status == "awaiting_approval"

    await engine.dispose()
