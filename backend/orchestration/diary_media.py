"""Generate and persist narration media for an approved diary version."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from backend.agents.diary_chatbot.write_script.base import ScriptGenerationAgent
from backend.agents.diary_chatbot.write_script.schemas import (
    DiaryData,
    ScriptOptions,
    WriteScriptInput,
)
from backend.repositories.sqlalchemy import SQLAlchemyDiaryRepository
from backend.services.avatar import AvatarAdapter
from backend.services.storage import StorageAdapter
from backend.services.video.metadata import probe_video_duration_seconds
from backend.services.voice import VoiceAdapter


class DiaryMediaResult(BaseModel):
    version_id: str
    script_id: str
    audio_id: str
    narration_text: str
    emotion: str | None = None
    target_duration_seconds: int
    audio_url: str
    video_id: str
    video_url: str
    duration_seconds: int
    character_id: str
    voice_id: str
    status: str = "completed"


class DiaryMediaOrchestrator:
    def __init__(
        self,
        *,
        script_agent: ScriptGenerationAgent,
        voice_adapter: VoiceAdapter,
        avatar_adapter: AvatarAdapter,
        storage_adapter: StorageAdapter,
        config: dict[str, Any],
        video_duration_probe: Callable[[bytes], Awaitable[int]] = probe_video_duration_seconds,
    ) -> None:
        self._script_agent = script_agent
        self._voice = voice_adapter
        self._avatar = avatar_adapter
        self._storage = storage_adapter
        self._config = config
        self._video_duration_probe = video_duration_probe

    async def run(
        self,
        *,
        version_id: str,
        voice_id: str,
        character_id: str,
        character_image_path: str | Path,
        repository: SQLAlchemyDiaryRepository,
        target_duration_seconds: int = 30,
        tone: str = "따뜻한 회상",
    ) -> DiaryMediaResult:
        diary = await repository.get_approved_version(version_id)
        if diary is None:
            raise PermissionError(
                "script and audio generation require an approved diary"
            )

        script = await repository.get_narration_script(version_id)
        if (
            script is None
            or script.status != "completed"
            or not script.narration_text
        ):
            script_id = (
                script.script_id
                if script is not None
                else f"script_{uuid4().hex[:20]}"
            )
            script = await repository.start_narration_script(
                script_id=script_id,
                diary_version_id=version_id,
                tone=tone,
                target_duration_seconds=target_duration_seconds,
                llm_model=self._config["llm"]["model_reasoning"],
            )

            try:
                generated = await self._script_agent.generate(
                    WriteScriptInput(
                        diary_id=version_id,
                        diary=DiaryData(
                            title=diary.title.strip() or "오늘의 일기",
                            content=diary.content,
                            paragraphs=diary.paragraphs or [diary.content],
                            summary=diary.summary,
                            emotion_tags=diary.emotion_tags or [],
                            evidence_input_ids=diary.evidence_input_ids or [],
                        ),
                        script_options=ScriptOptions(
                            target_duration_seconds=target_duration_seconds,
                            tone=tone,
                        ),
                    ),
                    script_id=script.script_id,
                )
                script = await repository.complete_narration_script(
                    script.script_id,
                    narration_text=generated.narration_text,
                    emotion=generated.emotion,
                )
            except Exception as exc:
                await repository.fail_narration_script(
                    script.script_id,
                    type(exc).__name__,
                )
                raise

        existing_audio = await repository.get_completed_diary_audio(
            script_id=script.script_id,
            voice_id=voice_id,
        )
        audio_bytes: bytes | None = None
        if existing_audio is not None and existing_audio.audio_url:
            audio = existing_audio
        else:
            audio_id = f"audio_{uuid4().hex[:20]}"
            audio = await repository.start_diary_audio(
                audio_id=audio_id,
                script_id=script.script_id,
                voice_id=voice_id,
            )

            try:
                audio_bytes = await self._voice.synthesize(
                    script.narration_text,
                    voice_id=voice_id,
                    emotion=script.emotion,
                )
                stored = await self._storage.upload(
                    audio_bytes,
                    object_name=f"diary-audios/{version_id}/{audio_id}.mp3",
                    mime_type="audio/mpeg",
                )
                audio = await repository.complete_diary_audio(
                    audio.audio_id,
                    object_key=stored.object_key,
                    audio_url=stored.url,
                    audio_hash=stored.content_hash,
                    audio_size=stored.size_bytes,
                    audio_mime_type=stored.mime_type,
                )
            except Exception as exc:
                await repository.fail_diary_audio(
                    audio.audio_id,
                    type(exc).__name__,
                )
                raise

        if not audio.audio_url:
            raise RuntimeError("completed diary audio is missing its storage URL")

        existing_video = await repository.get_avatar_video(version_id)
        if (
            existing_video is not None
            and existing_video.status == "completed"
            and existing_video.storage_url
        ):
            duration_seconds = existing_video.duration
            if not duration_seconds:
                if existing_video.object_key:
                    existing_video_bytes = await self._storage.download(
                        object_name=existing_video.object_key
                    )
                    duration_seconds = await self._video_duration_probe(
                        existing_video_bytes
                    )
                else:
                    duration_seconds = script.target_duration_seconds
                existing_video = await repository.update_avatar_video_duration(
                    existing_video.video_id,
                    duration=duration_seconds,
                )
            return DiaryMediaResult(
                version_id=version_id,
                script_id=script.script_id,
                audio_id=audio.audio_id,
                narration_text=script.narration_text,
                emotion=script.emotion,
                target_duration_seconds=script.target_duration_seconds,
                audio_url=audio.audio_url,
                video_id=existing_video.video_id,
                video_url=existing_video.storage_url,
                duration_seconds=duration_seconds,
                character_id=character_id,
                voice_id=voice_id,
            )

        video_id = (
            existing_video.video_id
            if existing_video is not None
            else f"video_{uuid4().hex[:20]}"
        )
        video = await repository.start_avatar_video(
            video_id=video_id,
            version_id=version_id,
        )
        try:
            if audio_bytes is None:
                if audio.object_key:
                    audio_bytes = await self._storage.download(
                        object_name=audio.object_key
                    )
                else:
                    # Compatibility with rows created before object_key was persisted.
                    audio_bytes = await self._voice.synthesize(
                        script.narration_text,
                        voice_id=voice_id,
                        emotion=script.emotion,
                    )
            video_bytes = await self._avatar.render(
                audio_bytes,
                version_id=version_id,
                source_image=character_image_path,
            )
            duration_seconds = await self._video_duration_probe(video_bytes)
            stored_video = await self._storage.upload(
                video_bytes,
                object_name=f"diary-videos/{version_id}/{video.video_id}.mp4",
                mime_type="video/mp4",
            )
            video = await repository.complete_avatar_video(
                video.video_id,
                object_key=stored_video.object_key,
                storage_url=stored_video.url,
                video_hash=stored_video.content_hash,
                video_size=stored_video.size_bytes,
                video_mime_type=stored_video.mime_type,
                duration=duration_seconds,
            )
        except Exception as exc:
            await repository.fail_avatar_video(video.video_id, type(exc).__name__)
            raise

        if not video.storage_url:
            raise RuntimeError("completed avatar video is missing its storage URL")

        return DiaryMediaResult(
            version_id=version_id,
            script_id=script.script_id,
            audio_id=audio.audio_id,
            narration_text=script.narration_text,
            emotion=script.emotion,
            target_duration_seconds=script.target_duration_seconds,
            audio_url=audio.audio_url,
            video_id=video.video_id,
            video_url=video.storage_url,
            duration_seconds=video.duration,
            character_id=character_id,
            voice_id=voice_id,
        )
