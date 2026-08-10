from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class WorkflowStage(str, Enum):
    COLLECTING = "collecting"
    NEEDS_CLARIFICATION = "needs_clarification"
    AWAITING_SUMMARY_CONFIRMATION = "awaiting_summary_confirmation"
    AWAITING_MORE_CONTENT = "awaiting_more_content"
    ADDING_MORE_CONTENT = "adding_more_content"
    AWAITING_CORRECTION = "awaiting_correction"
    READY_TO_GENERATE = "ready_to_generate"
    DRAFTED = "drafted"
    APPROVED = "approved"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class Evidence(BaseModel):
    input_id: str
    excerpt: str | None = None


class EmotionMention(BaseModel):
    label: str = Field(min_length=1, description="일기 표시에 사용할 자연스러운 감정 표현")
    excerpt: str = Field(min_length=1, description="사용자 입력에서 그대로 발췌한 감정 구절")
    input_id: str = Field(min_length=1, description="excerpt가 나온 원본 입력 ID")


class EventCandidate(BaseModel):
    event: str
    time: str | None = None
    people: list[str] = Field(default_factory=list)
    location: str | None = None
    actions: list[str] = Field(default_factory=list)
    emotions: list[EmotionMention] = Field(
        default_factory=list,
        description="원문 발췌와 입력 ID로 검증 가능한 감정 표현만 허용한다.",
    )
    evidence: list[Evidence] = Field(min_length=1)


class InformationCoverage(BaseModel):
    has_person: bool
    has_location: bool
    has_emotion: bool
    sufficient: bool
    missing_fields: list[str] = Field(default_factory=list)


class ImageClarityNote(BaseModel):
    input_id: str
    unclear: bool
    reason: str | None = None


class ImageObservation(BaseModel):
    input_id: str
    description: str = Field(min_length=1)
    observed_facts: list[str] = Field(default_factory=list)
    related_event: str | None = None


class MultimodalContext(BaseModel):
    session_id: str
    user_message: str | None = None
    text_inputs: dict[str, str] = Field(default_factory=dict)
    image_urls: dict[str, str] = Field(default_factory=dict)
    audio_transcripts: dict[str, str] = Field(default_factory=dict)
    prior_events: list[EventCandidate] = Field(default_factory=list)
    prior_reactions: list[str] = Field(default_factory=list)
    skipped_fields: list[str] = Field(default_factory=list)


class FactExtractionResult(BaseModel):
    events: list[EventCandidate]
    coverage: InformationCoverage
    image_observations: list[ImageObservation] = Field(default_factory=list)
    image_clarity: list[ImageClarityNote] = Field(default_factory=list)
    model: str = "HCX-005"


class TurnResponse(BaseModel):
    reaction: str = Field(min_length=1)
    question: str | None = None

    @field_validator("reaction")
    @classmethod
    def reaction_must_not_contain_question(cls, value: str) -> str:
        if "?" in value or "？" in value:
            raise ValueError("reaction must not contain a question")
        return value


class ChatbotTurnResult(FactExtractionResult):
    """A fact extraction plus the separately composed user-facing response."""

    response: TurnResponse = Field(
        default_factory=lambda: TurnResponse(reaction="이야기를 기록했어요.")
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_response(cls, data):
        if isinstance(data, dict) and "response" not in data:
            questions = data.get("follow_up_questions") or []
            data = {
                **data,
                "response": {
                    "reaction": data.get("reaction") or "이야기를 기록했어요.",
                    "question": questions[0] if questions else None,
                },
            }
        return data

    @property
    def reaction(self) -> str:
        return self.response.reaction

    @property
    def follow_up_questions(self) -> list[str]:
        return [self.response.question] if self.response.question else []

    @property
    def action_text(self) -> str:
        return "부족한 정보를 확인할게요." if self.response.question else "이대로 일기를 작성해 드릴까요?"


class DiaryDraft(BaseModel):
    title: str
    paragraphs: list[str] = Field(min_length=3, max_length=7)
    summary: str
    content: str
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
