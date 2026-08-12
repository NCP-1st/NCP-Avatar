from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.embedding.service import DiaryEmbeddingService
from database.models import Base, DiaryEmbedding, DiarySession, DiaryVersion, User


class StubEmbedder:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.inputs: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.inputs.append(text)
        if self.fail:
            raise RuntimeError("sensitive provider response")
        return [0.25] * 1024


async def _session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


async def _insert_approved_diary(db, version_id: str = "version-1") -> None:
    db.add(User(user_id="embedding-user"))
    db.add(
        DiarySession(
            session_id="embedding-session",
            user_id="embedding-user",
            diary_date=date(2026, 8, 12),
        )
    )
    db.add(
        DiaryVersion(
            version_id=version_id,
            session_id="embedding-session",
            title="승인된 일기",
            summary="짧은 요약",
            content="친구와 성수동에서 즐거운 하루를 보냈다.",
            approved=True,
        )
    )
    await db.commit()


@pytest.mark.anyio
async def test_index_diary_stores_content_embedding_and_is_idempotent() -> None:
    engine, factory = await _session_factory()
    try:
        async with factory() as db:
            await _insert_approved_diary(db)
            embedder = StubEmbedder()
            service = DiaryEmbeddingService(db, embedder)

            await service.index_diary(
                version_id="version-1",
                content="친구와 성수동에서 즐거운 하루를 보냈다.",
            )
            await service.index_diary(
                version_id="version-1",
                content="수정된 승인 일기 본문",
            )

            stored = await db.get(DiaryEmbedding, "version-1")
            assert stored is not None
            assert len(stored.embedding) == 1024
            assert embedder.inputs == [
                "친구와 성수동에서 즐거운 하루를 보냈다.",
                "수정된 승인 일기 본문",
            ]
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_embedding_failure_does_not_escape_or_remove_approved_diary() -> None:
    engine, factory = await _session_factory()
    try:
        async with factory() as db:
            await _insert_approved_diary(db, "version-failed")
            service = DiaryEmbeddingService(db, StubEmbedder(fail=True))

            await service.index_diary(
                version_id="version-failed",
                content="승인은 유지되어야 하는 본문",
            )

            diary = await db.get(DiaryVersion, "version-failed")
            assert diary is not None
            assert diary.approved is True
            assert await db.get(DiaryEmbedding, "version-failed") is None
    finally:
        await engine.dispose()
