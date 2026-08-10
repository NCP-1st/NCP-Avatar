"""대본 작성 에이전트의 입출력 스키마."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Emotion = Literal["중립", "슬픔", "기쁨", "분노"]


class DiaryData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    story: str = Field(min_length=1)
    feelings: list[str] = Field(min_length=1)


class ChatMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    people: list[str] = Field(default_factory=list)
    places: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    dominant_feeling: str
    keywords: list[str] = Field(default_factory=list)


class ScriptOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_duration_seconds: int = Field(default=30, ge=10, le=120)
    tone: str = "따뜻한 회상"


class WriteScriptInput(BaseModel):
    """완성된 일기와 채팅 메타데이터를 담는 대본 생성 입력."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    diary_id: str
    diary_date: str
    diary_version_id: str
    diary: DiaryData
    chat_metadata: ChatMetadata
    script_options: ScriptOptions = Field(default_factory=ScriptOptions)
    approved: bool


class NarrationScript(BaseModel):
    """대본 작성 에이전트가 반환하는 최종 구조화 결과."""

    model_config = ConfigDict(extra="forbid")

    script_id: str
    diary_id: str
    narration_text: str = Field(min_length=1)
    target_duration_seconds: int = Field(ge=10, le=120)
    emotion: Emotion
