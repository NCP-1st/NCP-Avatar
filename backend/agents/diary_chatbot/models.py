from enum import Enum

from pydantic import BaseModel, Field


class WorkflowStage(str, Enum):
    COLLECTING = "collecting"
    NEEDS_CLARIFICATION = "needs_clarification"
    READY_TO_GENERATE = "ready_to_generate"
    DRAFTED = "drafted"
    APPROVED = "approved"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class Evidence(BaseModel):
    input_id: str
    excerpt: str | None = None


class EventCandidate(BaseModel):
    event: str
    time: str | None = None
    people: list[str] = Field(default_factory=list)
    place: str | None = None
    actions: list[str] = Field(default_factory=list)
    emotions: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(min_length=1)


class InformationCoverage(BaseModel):
    has_event: bool
    has_time: bool
    has_emotion: bool
    sufficient: bool
    missing_fields: list[str] = Field(default_factory=list)


class MultimodalContext(BaseModel):
    session_id: str
    user_message: str | None = None
    text_inputs: dict[str, str] = Field(default_factory=dict)
    image_urls: dict[str, str] = Field(default_factory=dict)
    audio_transcripts: dict[str, str] = Field(default_factory=dict)


class ChatbotTurnResult(BaseModel):
    reply: str
    events: list[EventCandidate]
    coverage: InformationCoverage
    follow_up_questions: list[str] = Field(default_factory=list, max_length=3)
    model: str = "HCX-005"


class DiaryDraft(BaseModel):
    title: str
    paragraphs: list[str] = Field(min_length=3, max_length=7)
    summary: str
    narration_script: str
    emotion_tags: list[str]
    evidence_input_ids: list[str]
    model: str = "HCX-007"


class DiaryVersion(DiaryDraft):
    version_id: str
    session_id: str
    approved: bool = False


class RenderResult(BaseModel):
    version_id: str
    audio_url: str
    video_url: str
