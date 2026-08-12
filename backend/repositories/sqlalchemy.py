"""SQLAlchemy persistence helpers for the diary HTTP workflow."""

from datetime import date
from typing import Optional
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.counsel_chatbot.schemas import CounselTrace, CounselTurn
from backend.agents.diary_chatbot.models import DiaryVersion
from backend.api.schemas import NormalizedInputItem
from database.models import (
    CounselSession,
    CounselTurnTrace,
    AvatarVideo,
    DiaryAudio,
    DiaryInput,
    DiarySession,
    NarrationScript,
    User,
)
from database.models import CounselTurn as ORMCounselTurn
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

    async def get_version_media_object_keys(
        self,
        *,
        session_id: str,
        version_id: str,
    ) -> list[str]:
        stored = await self.db.get(ORMDiaryVersion, version_id)
        if stored is None or stored.session_id != session_id:
            raise ValueError("diary version to delete was not found in this session")

        videos = list(
            (
                await self.db.execute(
                    select(AvatarVideo).where(AvatarVideo.version_id == version_id)
                )
            ).scalars()
        )
        script = await self.get_narration_script(version_id)
        audios = []
        if script is not None:
            audios = list(
                (
                    await self.db.execute(
                        select(DiaryAudio).where(DiaryAudio.script_id == script.script_id)
                    )
                ).scalars()
            )

        if any(item.status == "processing" for item in [*videos, *audios]) or (
            script is not None and script.status == "processing"
        ):
            raise RuntimeError("media generation is still processing")

        return sorted(
            {
                item.object_key
                for item in [*videos, *audios]
                if item.object_key
            }
        )

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

    async def get_approved_version(
        self,
        version_id: str,
    ) -> ORMDiaryVersion | None:
        return await self.db.scalar(
            select(ORMDiaryVersion).where(
                ORMDiaryVersion.version_id == version_id,
                ORMDiaryVersion.approved.is_(True),
            )
        )

    async def get_narration_script(
        self,
        diary_version_id: str,
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

    async def fail_narration_script(
        self,
        script_id: str,
        error_code: str,
    ) -> None:
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
        voice_id: str | None,
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

    async def fail_diary_audio(
        self,
        audio_id: str,
        error_code: str,
    ) -> None:
        audio = await self.db.get(DiaryAudio, audio_id)
        if audio is not None:
            audio.status = "failed"
            audio.error_code = error_code
            await self.db.commit()

    async def get_avatar_video(self, version_id: str) -> AvatarVideo | None:
        return await self.db.scalar(
            select(AvatarVideo)
            .where(AvatarVideo.version_id == version_id)
            .order_by(AvatarVideo.created_at.desc())
            .limit(1)
        )

    async def start_avatar_video(
        self,
        *,
        video_id: str,
        version_id: str,
    ) -> AvatarVideo:
        video = await self.get_avatar_video(version_id)
        if video is None:
            video = AvatarVideo(
                video_id=video_id,
                version_id=version_id,
                status="processing",
            )
            self.db.add(video)
        else:
            video.status = "processing"
            video.error_code = None
        await self.db.commit()
        return video

    async def complete_avatar_video(
        self,
        video_id: str,
        *,
        object_key: str | None,
        storage_url: str,
        video_hash: str,
        video_size: int,
        video_mime_type: str,
        duration: int,
    ) -> AvatarVideo:
        video = await self.db.get(AvatarVideo, video_id)
        if video is None:
            raise LookupError("avatar video not found")
        video.status = "completed"
        video.object_key = object_key
        video.storage_url = storage_url
        video.video_hash = video_hash
        video.video_size = video_size
        video.video_mime_type = video_mime_type
        video.duration = duration
        video.error_code = None
        await self.db.commit()
        return video

    async def fail_avatar_video(self, video_id: str, error_code: str) -> None:
        video = await self.db.get(AvatarVideo, video_id)
        if video is not None:
            video.status = "failed"
            video.error_code = error_code
            await self.db.commit()

    async def update_avatar_video_duration(
        self,
        video_id: str,
        *,
        duration: int,
    ) -> AvatarVideo:
        video = await self.db.get(AvatarVideo, video_id)
        if video is None:
            raise LookupError("avatar video not found")
        video.duration = duration
        await self.db.commit()
        return video

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

# 세션 safety_level 은 "이 세션에서 도달한 가장 높은 등급"의 롤업이다.
# 한 번 올라간 등급은 내려오지 않는다 — 사용자가 화제를 돌렸다고 해서
# 위기 세션이 평범한 세션으로 되돌아가면 안 된다.
_SAFETY_RANK = {"normal": 0, "caution": 1, "crisis": 2}


class SQLAlchemyConversationStore:
    """상담 대화 이력 저장소 (PostgreSQL).

    인메모리 스텁과 달리 프로세스가 죽어도 이력이 남고, 워커가 여러 개여도
    한 벌만 존재한다. 클라이언트가 이력을 들고 다니지 않으므로 이력 위조로
    안전 규칙을 우회할 수 없다.

    소유권 확인은 저장소의 책임이다: user_id 가 맞지 않으면 읽기는 빈 목록,
    쓰기는 PermissionError.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def load_turns(
        self,
        *,
        counsel_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[CounselTurn]:
        session = await self.db.get(CounselSession, counsel_id)
        if session is not None and session.user_id != user_id:
            return []  # 남의 counsel_id 를 찍어 대화를 읽어가려는 시도

        rows = (
            await self.db.execute(
                select(ORMCounselTurn)
                .where(ORMCounselTurn.counsel_id == counsel_id)
                .order_by(desc(ORMCounselTurn.turn_id))
                .limit(limit)
            )
        ).scalars().all()

        # 최근 N개를 뽑되 흐름은 오래된 순으로 돌려준다.
        return [
            CounselTurn(role=row.role, content=row.content, stage=row.stage)
            for row in reversed(rows)
        ]

    async def append_turn(
        self,
        *,
        counsel_id: str,
        user_id: str,
        turn: CounselTurn,
        trace: CounselTrace | None = None,
        safety_level: str | None = None,
    ) -> None:
        """대화 한 줄을 덧붙인다. 세션이 없으면 만든다.

        `trace` 가 오면 어시스턴트 턴과 같은 트랜잭션으로 트레이스를 남긴다.
        턴과 트레이스는 1:1이고 같은 순간에 만들어지므로 따로 커밋하면
        한쪽만 남을 수 있다.
        """
        session = await self._session_for_write(counsel_id, user_id)

        orm_turn = ORMCounselTurn(
            counsel_id=counsel_id,
            user_id=user_id,
            role=turn.role,
            content=turn.content,
            stage=turn.stage,
        )
        self.db.add(orm_turn)
        session.last_active_at = func.now()

        if safety_level is not None:
            self._raise_safety(session, safety_level)

        if trace is not None:
            await self.db.flush()  # orm_turn.turn_id 확보
            self.db.add(
                CounselTurnTrace(
                    turn_id=orm_turn.turn_id,
                    trace_id=trace.trace_id,
                    model=trace.model,
                    result_code=trace.result_code,
                    # 이번 턴의 등급이 있으면 그걸 쓴다. 세션 롤업은 이미
                    # 올라가 있을 수 있어 턴별 감사에는 부정확하다.
                    safety_level=safety_level or session.safety_level,
                    stage=trace.stage,
                    emotion=trace.emotion,
                    latency_ms=trace.latency_ms,
                    knowledge_count=trace.knowledge_count,
                    ontology_count=trace.ontology_count,
                    event_count=trace.event_count,
                    guardrail_hits=trace.guardrail_hits,
                    stage_ms=trace.stage_ms,
                    error_detail=trace.error_detail,
                )
            )

        await self.db.commit()

    async def mark_crisis(self, *, counsel_id: str, user_id: str) -> None:
        session = await self._session_for_write(counsel_id, user_id)
        session.is_crisis = True
        session.safety_level = "crisis"
        await self.db.commit()

    async def is_crisis(self, *, counsel_id: str, user_id: str) -> bool:
        session = await self.db.get(CounselSession, counsel_id)
        return bool(session and session.user_id == user_id and session.is_crisis)

    async def _session_for_write(self, counsel_id: str, user_id: str) -> CounselSession:
        """쓰기 대상 세션을 가져온다. 없으면 만들고, 남의 것이면 거절한다."""
        session = await self.db.get(CounselSession, counsel_id)
        if session is None:
            # counsel_turns.user_id 가 users 를 참조하므로 사용자 행이 먼저 있어야 한다.
            if await self.db.get(User, user_id) is None:
                self.db.add(User(user_id=user_id))
                await self.db.flush()
            session = CounselSession(counsel_id=counsel_id, user_id=user_id)
            self.db.add(session)
            await self.db.flush()
        elif session.user_id != user_id:
            raise PermissionError("다른 사용자의 상담 세션에는 쓸 수 없습니다")
        return session

    @staticmethod
    def _raise_safety(session: CounselSession, level: str) -> None:
        current = _SAFETY_RANK.get(session.safety_level, 0)
        if _SAFETY_RANK.get(level, 0) > current:
            session.safety_level = level
