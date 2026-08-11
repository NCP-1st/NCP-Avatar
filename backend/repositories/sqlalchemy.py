"""SQLAlchemy persistence helpers for the diary HTTP workflow."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.diary_chatbot.models import DiaryVersion
from backend.api.schemas import NormalizedInputItem
from database.models import DiaryAudio, DiaryChat, DiaryInput, DiarySession, NarrationScript, User
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

    async def approve_version(self, version_id: str) -> bool:
        stored = await self.db.get(ORMDiaryVersion, version_id)
        if stored is None:
            return False
        stored.approved = True
        await self.db.commit()
        return True

    async def get_approved_version(
        self, version_id: str
    ) -> ORMDiaryVersion | None:
        return await self.db.scalar(
            select(ORMDiaryVersion).where(
                ORMDiaryVersion.version_id == version_id,
                ORMDiaryVersion.approved.is_(True),
            )
        )

    async def get_narration_script(
        self, diary_version_id: str
    ) -> NarrationScript | None:
        return await self.db.scalar(
            select(NarrationScript).where(
                NarrationScript.diary_version_id == diary_version_id
            )
        )

    async def start_narration_script(
        self,
        *,
        script_id: str,
        diary_version_id: str,
        tone: str,
        target_duration_seconds: int,
        llm_model: str,
    ) -> NarrationScript:
        script = await self.get_narration_script(diary_version_id)
        if script is None:
            script = NarrationScript(
                script_id=script_id,
                diary_version_id=diary_version_id,
                tone=tone,
                target_duration_seconds=target_duration_seconds,
                status="processing",
                llm_model=llm_model,
            )
            self.db.add(script)
        else:
            script.status = "processing"
            script.error_code = None
            script.tone = tone
            script.target_duration_seconds = target_duration_seconds
            script.llm_model = llm_model
        await self.db.commit()
        return script

    async def complete_narration_script(
        self,
        script_id: str,
        *,
        narration_text: str,
        emotion: str,
    ) -> NarrationScript:
        script = await self.db.get(NarrationScript, script_id)
        if script is None:
            raise LookupError("narration script not found")
        script.narration_text = narration_text
        script.emotion = emotion
        script.status = "completed"
        script.error_code = None
        await self.db.commit()
        return script

    async def fail_narration_script(self, script_id: str, error_code: str) -> None:
        script = await self.db.get(NarrationScript, script_id)
        if script is not None:
            script.status = "failed"
            script.error_code = error_code
            await self.db.commit()

    async def start_diary_audio(
        self,
        *,
        audio_id: str,
        script_id: str,
        voice_id: str,
    ) -> DiaryAudio:
        audio = DiaryAudio(
            audio_id=audio_id,
            script_id=script_id,
            voice_id=voice_id,
            status="processing",
        )
        self.db.add(audio)
        await self.db.commit()
        return audio

    async def get_completed_diary_audio(
        self,
        *,
        script_id: str,
        voice_id: str,
    ) -> DiaryAudio | None:
        return await self.db.scalar(
            select(DiaryAudio)
            .where(
                DiaryAudio.script_id == script_id,
                DiaryAudio.voice_id == voice_id,
                DiaryAudio.status == "completed",
            )
            .order_by(DiaryAudio.created_at.desc())
            .limit(1)
        )

    async def complete_diary_audio(
        self,
        audio_id: str,
        *,
        object_key: str | None,
        audio_url: str,
        audio_hash: str,
        audio_size: int,
        audio_mime_type: str,
    ) -> DiaryAudio:
        audio = await self.db.get(DiaryAudio, audio_id)
        if audio is None:
            raise LookupError("diary audio not found")
        audio.status = "completed"
        audio.object_key = object_key
        audio.audio_url = audio_url
        audio.audio_hash = audio_hash
        audio.audio_size = audio_size
        audio.audio_mime_type = audio_mime_type
        audio.error_code = None
        await self.db.commit()
        return audio

    async def fail_diary_audio(self, audio_id: str, error_code: str) -> None:
        audio = await self.db.get(DiaryAudio, audio_id)
        if audio is not None:
            audio.status = "failed"
            audio.error_code = error_code
            await self.db.commit()

    async def _ensure_user(self, user_id: str) -> None:
        if await self.db.get(User, user_id) is None:
            self.db.add(User(user_id=user_id))
            await self.db.flush()
