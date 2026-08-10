from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class InputType(str, Enum):
    PHOTO = "photo"
    AUDIO = "audio"
    TEXT = "text"


class ProcessingStatus(str, Enum):
    OK = "ok"
    FAILED = "failed"


class CreateSessionRequest(BaseModel):
    user_id: str
    diary_date: date


class DiarySession(BaseModel):
    session_id: str
    user_id: str
    diary_date: date
    status: str = "collecting"


class InputItemRequest(BaseModel):
    input_id: str
    type: InputType
    text: str | None = None
    file_base64: str | None = None
    mime_type: str | None = None
    duration_seconds: float | None = Field(default=None, gt=0)
    captured_at: datetime | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "InputItemRequest":
        if self.type is InputType.TEXT and not self.text:
            raise ValueError("text input requires text")
        if self.type is not InputType.TEXT and not self.file_base64:
            raise ValueError("media input requires file_base64")
        if self.type is InputType.AUDIO and self.duration_seconds is not None and self.duration_seconds > 60:
            raise ValueError("CSR audio must not exceed 60 seconds")
        return self


class AddInputsRequest(BaseModel):
    items: list[InputItemRequest] = Field(min_length=1, max_length=10)


class NormalizedInputItem(BaseModel):
    input_id: str
    type: InputType
    storage_url: str | None = None
    content_hash: str | None = None
    size_bytes: int | None = None
    mime_type: str | None = None
    transcript: str | None = None
    transcript_confirmed: bool = False
    captured_at: datetime | None = None
    status: ProcessingStatus
    error_code: str | None = None
    error_reason: str | None = None
    provider_meta: dict[str, str | float] = Field(default_factory=dict)


class PreprocessResult(BaseModel):
    session_id: str
    items: list[NormalizedInputItem]
    error_count: int


class ConfirmTranscriptRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=5000)

    @field_validator("transcript")
    @classmethod
    def normalize_transcript(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("transcript must not be blank")
        return normalized


class ConfirmTranscriptResponse(BaseModel):
    session_id: str
    input_id: str
    transcript: str
    transcript_confirmed: bool


class DiaryChatRequest(BaseModel):
    message: str = Field(default="", max_length=2000)
    input_ids: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_chat_payload(self) -> "DiaryChatRequest":
        if not self.message.strip() and not self.input_ids:
            raise ValueError("message or input_ids is required")
        return self


class DiaryChatResponse(BaseModel):
    session_id: str
    stage: str
    questions_asked_count: int
    turn: dict
    review_summary: str | None = None


class DiaryReviewRequest(BaseModel):
    action: str

    @model_validator(mode="after")
    def validate_action(self) -> "DiaryReviewRequest":
        allowed = {"summary_yes", "summary_no", "more_yes", "more_no", "skip_current"}
        if self.action not in allowed:
            raise ValueError("unsupported review action")
        return self


class DiaryReviewResponse(BaseModel):
    session_id: str
    stage: str
    review_summary: str | None = None
    turn: dict | None = None


class GenerationJobResponse(BaseModel):
    job_id: str
    status: str


class GenerationJobStatus(BaseModel):
    job_id: str
    status: str
    result: dict | None = None
    error_code: str | None = None
