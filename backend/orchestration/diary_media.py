"""Approved diary to narration script and TTS audio orchestration."""

from __future__ import annotations

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
from backend.services.storage import StorageAdapter
from backend.services.voice import VoiceAdapter


class DiaryMediaResult(BaseModel):
    version_id: str
    script_id: str
    audio_id: str
    audio_url: str
    narration_text: str
    emotion: str | None = None
    target_duration_seconds: int
    status: str = "completed"


class DiaryMediaOrchestrator:
    """Run one approved-diary media cycle while persisting each stage."""

    def __init__(
        self,
        *,
        script_agent: ScriptGenerationAgent,
        voice_adapter: VoiceAdapter,
        storage_adapter: StorageAdapter,
        config: dict[str, Any],
    ) -> None:
        self._script_agent = script_agent
        self._voice = voice_adapter
        self._storage = storage_adapter
        self._config = config

    async def run(
        self,
        *,
        version_id: str,
        voice_id: str,
        repository: SQLAlchemyDiaryRepository,
        target_duration_seconds: int = 30,
        tone: str = "따뜻한 회상",
    ) -> DiaryMediaResult:
        diary = await repository.get_approved_version(version_id)
        if diary is None:
            raise PermissionError("script and audio generation require an approved diary")

        script = await repository.get_narration_script(version_id)
        if script is None or script.status != "completed" or not script.narration_text:
            requested_script_id = script.script_id if script else f"script_{uuid4().hex[:20]}"
            script = await repository.start_narration_script(
                script_id=requested_script_id,
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
                            title=diary.title,
                            content=diary.content,
                            paragraphs=diary.paragraphs or [],
                            summary=diary.summary,
                            emotion_tags=diary.emotion_tags,
                            evidence_input_ids=diary.evidence_input_ids,
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
                    script.script_id, type(exc).__name__
                )
                raise

        existing_audio = await repository.get_completed_diary_audio(
            script_id=script.script_id,
            voice_id=voice_id,
        )
        if existing_audio is not None and existing_audio.audio_url:
            return DiaryMediaResult(
                version_id=version_id,
                script_id=script.script_id,
                audio_id=existing_audio.audio_id,
                audio_url=existing_audio.audio_url,
                narration_text=script.narration_text,
                emotion=script.emotion,
                target_duration_seconds=script.target_duration_seconds,
            )

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
            await repository.fail_diary_audio(audio.audio_id, type(exc).__name__)
            raise

        if not audio.audio_url:
            raise RuntimeError("completed diary audio is missing its storage URL")
        return DiaryMediaResult(
            version_id=version_id,
            script_id=script.script_id,
            audio_id=audio.audio_id,
            audio_url=audio.audio_url,
            narration_text=script.narration_text,
            emotion=script.emotion,
            target_duration_seconds=script.target_duration_seconds,
        )
