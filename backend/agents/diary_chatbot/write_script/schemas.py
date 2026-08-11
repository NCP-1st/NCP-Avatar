"""대본 작성 에이전트의 입출력 스키마."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Emotion = Literal["중립", "슬픔", "기쁨", "분노"]


class DiaryData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    paragraphs: list[str] = Field(default_factory=list, max_length=7)
    summary: str = Field(min_length=1)
    emotion_tags: list[str] = Field(default_factory=list)
    evidence_input_ids: list[str] = Field(default_factory=list)


class ScriptOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_duration_seconds: int = Field(default=30, ge=10, le=120)
    tone: str = "따뜻한 회상"


class WriteScriptInput(BaseModel):
    """완성된 일기를 담는 나레이션 미리보기 생성 입력."""

    model_config = ConfigDict(extra="forbid")

    diary_id: str
    diary: DiaryData
    script_options: ScriptOptions = Field(default_factory=ScriptOptions)


class NarrationScript(BaseModel):
    """대본 작성 에이전트가 반환하는 최종 구조화 결과."""

    model_config = ConfigDict(extra="forbid")

    script_id: str
    diary_id: str
    narration_text: str = Field(min_length=1)
    target_duration_seconds: int = Field(ge=10, le=120)
    emotion: Emotion
