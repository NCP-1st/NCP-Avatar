"""SQLAlchemy persistence helpers for the diary HTTP workflow."""

from datetime import date
from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.diary_chatbot.models import DiaryVersion
from backend.api.schemas import NormalizedInputItem
from database.models import DiaryInput, DiarySession, User
from database.models import DiaryVersion as ORMDiaryVersion


class SQLAlchemyDiaryRepository:
    MAX_VERSIONS_PER_SESSION = 3

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_existing_session(
        self, *, user_id: str, diary_date: date
    ) -> Optional[str]:
        result = await self.db.execute(
            select(DiarySession.session_id)
            .where(
                DiarySession.user_id == user_id,
                DiarySession.diary_date == diary_date,
            )
            .order_by(DiarySession.created_at.desc(), DiarySession.session_id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def save_session(
        self, *, session_id: str, user_id: str, diary_date: date
    ) -> None:
        await self._ensure_user(user_id)
        self.db.add(
            DiarySession(
                session_id=session_id,
                user_id=user_id,
                diary_date=diary_date,
                status="active",
            )
        )
        await self.db.commit()

    async def save_inputs(
        self, *, session_id: str, items: list[NormalizedInputItem]
    ) -> None:
        for item in items:
            existing = await self.db.get(DiaryInput, item.input_id)
            if existing is None:
                existing = DiaryInput(input_id=item.input_id, session_id=session_id)
                self.db.add(existing)
            existing.type = item.type.value
            # Inline data URLs are only a local HCX transport. Persisting the
            # Base64 payload would put the media itself in DB and overflow the
            # URL column. A real URL is stored only after Object Storage is used.
            existing.storage_url = (
                item.storage_url
                if item.storage_url and not item.storage_url.startswith("data:")
                else None
            )
            existing.transcript = item.transcript
            existing.captured_at = item.captured_at
        await self.db.commit()

    async def update_transcript(self, *, input_id: str, transcript: str) -> None:
        item = await self.db.get(DiaryInput, input_id)
        if item is not None:
            item.transcript = transcript
            await self.db.commit()

    async def save_version(self, version: DiaryVersion) -> None:
        count_result = await self.db.execute(
            select(func.count())
            .select_from(ORMDiaryVersion)
            .where(ORMDiaryVersion.session_id == version.session_id)
        )
        if count_result.scalar_one() >= self.MAX_VERSIONS_PER_SESSION:
            raise ValueError("이 세션에는 일기를 최대 3개까지만 저장할 수 있습니다.")
        self.db.add(
            ORMDiaryVersion(
                version_id=version.version_id,
                session_id=version.session_id,
                title=version.title,
                summary=version.summary,
                content=version.content,
                emotion_tags=version.emotion_tags,
                paragraphs=version.paragraphs,
                evidence_input_ids=version.evidence_input_ids,
                approved=version.approved,
            )
        )
        session = await self.db.get(DiarySession, version.session_id)
        if session is not None:
            session.status = "awaiting_approval"
        await self.db.commit()

    async def get_versions(self, session_id: str) -> list[DiaryVersion]:
        result = await self.db.execute(
            select(ORMDiaryVersion)
            .where(ORMDiaryVersion.session_id == session_id)
            .order_by(ORMDiaryVersion.created_at.asc(), ORMDiaryVersion.version_id.asc())
        )
        return [self._to_domain(stored) for stored in result.scalars()]

    async def get_version(self, version_id: str) -> DiaryVersion | None:
        stored = await self.db.get(ORMDiaryVersion, version_id)
        if stored is None:
            return None
        return self._to_domain(stored)

    async def delete_version(self, *, session_id: str, version_id: str) -> None:
        stored = await self.db.get(ORMDiaryVersion, version_id)
        if stored is None or stored.session_id != session_id:
            raise ValueError("삭제할 일기 후보가 이 세션에 없습니다.")

        was_approved = stored.approved
        await self.db.delete(stored)
        await self.db.flush()

        session = await self.db.get(DiarySession, session_id)
        if session is not None:
            remaining_result = await self.db.execute(
                select(func.count())
                .select_from(ORMDiaryVersion)
                .where(ORMDiaryVersion.session_id == session_id)
            )
            remaining_count = remaining_result.scalar_one()
            if was_approved:
                session.status = "awaiting_approval" if remaining_count else "active"
        await self.db.commit()

    async def finalize_session_versions(
        self, *, session_id: str, approved_version_id: str
    ) -> DiaryVersion:
        result = await self.db.execute(
            select(ORMDiaryVersion)
            .where(ORMDiaryVersion.session_id == session_id)
            .with_for_update()
        )
        stored_versions = list(result.scalars())
        selected = next(
            (item for item in stored_versions if item.version_id == approved_version_id),
            None,
        )
        if selected is None:
            raise ValueError("선택한 일기 버전이 이 세션에 없습니다.")
        for item in stored_versions:
            item.approved = item.version_id == approved_version_id
        session = await self.db.get(DiarySession, session_id)
        if session is not None:
            session.status = "completed"
        await self.db.commit()
        return self._to_domain(selected)

    @staticmethod
    def _to_domain(stored: ORMDiaryVersion) -> DiaryVersion:
        return DiaryVersion(
            version_id=stored.version_id,
            session_id=stored.session_id,
            title=stored.title,
            paragraphs=stored.paragraphs or [stored.content],
            summary=stored.summary,
            content=stored.content,
            emotion_tags=stored.emotion_tags or [],
            evidence_input_ids=stored.evidence_input_ids or [],
            approved=stored.approved,
        )

    async def _ensure_user(self, user_id: str) -> None:
        if await self.db.get(User, user_id) is None:
            self.db.add(User(user_id=user_id))
            await self.db.flush()

    async def mark_session_active(self, session_id: str) -> None:
        session = await self.db.get(DiarySession, session_id)
        if session is not None:
            session.status = "active"
            await self.db.commit()
