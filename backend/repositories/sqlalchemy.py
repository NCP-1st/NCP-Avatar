"""SQLAlchemy persistence helpers for the diary HTTP workflow."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.diary_chatbot.models import DiaryVersion
from backend.api.schemas import NormalizedInputItem
from database.models import DiaryChat, DiaryInput, DiarySession, User
from database.models import DiaryVersion as ORMDiaryVersion


class SQLAlchemyDiaryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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
            existing.storage_url = item.storage_url
            existing.transcript = item.transcript
            existing.captured_at = item.captured_at
        await self.db.commit()

    async def update_transcript(self, *, input_id: str, transcript: str) -> None:
        item = await self.db.get(DiaryInput, input_id)
        if item is not None:
            item.transcript = transcript
            await self.db.commit()

    async def save_chat_turn(
        self,
        *,
        session_id: str,
        user_id: str,
        user_chat: str,
        assistant_chat: str,
    ) -> None:
        self.db.add_all(
            [
                DiaryChat(
                    session_id=session_id,
                    user_id=user_id,
                    role="user",
                    chat=user_chat,
                ),
                DiaryChat(
                    session_id=session_id,
                    user_id=user_id,
                    role="assistant",
                    chat=assistant_chat,
                ),
            ]
        )
        await self.db.commit()

    async def save_version(self, version: DiaryVersion) -> None:
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
            session.status = "completed"
        await self.db.commit()

    async def get_version(self, version_id: str) -> DiaryVersion | None:
        stored = await self.db.get(ORMDiaryVersion, version_id)
        if stored is None:
            return None
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
