
from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "EMOTION_LABELS",
    "NEUTRAL_EMOTION",
    "ConversationState",
    "CounselDraft",
    "CounselEvidenceRef",
    "CounselHistory",
    "CounselHistoryTurn",
    "CounselReply",
    "CounselRequest",
    "CounselSessionSummary",
    "CounselStage",
    "CounselTrace",
    "CounselTurn",
    "EmotionReading",
    "ExtractedEvent",
    "MemoryScope",
    "ResultCode",
    "SafetyLevel",
]


class SafetyLevel(StrEnum):
    """대화 한 턴의 안전 등급."""

    NORMAL = "normal"
    CAUTION = "caution"  # 위험 신호 관찰 — 상담은 계속하되 안전 안내를 덧붙인다
    CRISIS = "crisis"  # 자해·타해 등 — 일반 상담 흐름을 중단한다


class CounselStage(StrEnum):


    OPENING = "opening"  # 처음 — 받아주고 하나 묻는다
    EXPLORING = "exploring"  # 더 듣는 중 — 공감이 기본, 질문은 필요할 때만
    CARING = "caring"  # 상황·감정이 잡혔다 — 정리해주고 하나 권한다
    CLOSING = "closing"  # 사용자가 마무리하려 한다


ResultCode = Literal[
    "ok",
    "crisis_redirect",  # 위기 감지 → 안전 안내로 대체
    "guardrail_rewrite",  # 금칙 표현 감지 → 재생성 후 통과
    "guardrail_blocked",  # 재생성 후에도 위반 → 안전 폴백 응답
    "llm_failed",  # 모델 호출 실패 → 폴백 응답
]


# 감정 라벨 목록. 일기 챗봇의 감정 태그와 같은 어휘를 써야 검색이 맞물린다.
# 바꿀 때는 일기 쪽 태그와 함께 맞춘다.
EMOTION_LABELS: tuple[str, ...] = (
    # 긍정
    "기쁨",
    "설렘",
    "뿌듯함",
    "후련함",
    "안도",
    "감사",
    "따뜻함",
    "평온",
    "기대",
    # 중립·혼재
    "무덤덤",
    "그리움",
    "혼란",
    "놀람",
    # 부정
    "부담",
    "불안",
    "초조",
    "답답함",
    "피로",
    "무기력",
    "외로움",
    "슬픔",
    "속상함",
    "서운함",
    "실망",
    "억울함",
    "화남",
    "부러움",
    "죄책감",
    "후회",
    "미안함",
    "걱정",
    "허탈",
    "원망",
    "안타까움",
    "부끄러움",
)

NEUTRAL_EMOTION = "무덤덤"


class MemoryScope(BaseModel):

    enabled: bool = True
    period_days: int = Field(default=30, ge=1, le=365)
    max_items: int = Field(default=5, ge=1, le=10)  # 모델 입력 최소화


class EmotionReading(BaseModel):

    # intensity·confidence에 기본값을 주지 않는다. 기본값이 있으면 JSON Schema의
    # required에서 빠지고, 모델이 그냥 생략해 버려 항상 기본값만 돌아온다.
    primary: str = Field(description="가장 두드러진 감정 하나. 허용 목록 안에서만 고른다")
    secondary: list[str] = Field(
        description="함께 보이는 감정 0~2개. 없으면 빈 배열. 허용 목록 안에서만",
    )
    intensity: int = Field(ge=1, le=5, description="감정의 세기 1~5. 반드시 채운다")
    confidence: float = Field(ge=0, le=1, description="판단 확신도 0~1. 반드시 채운다")
    evidence: str = Field(
        default="",
        description="그렇게 본 근거가 된 사용자의 표현. 사용자가 쓴 말에서 그대로 가져온다",
    )

    # 모델이 범위를 벗어난 값을 내는 일이 실제로 있다(intensity: -1 등). 그때
    # 턴 전체를 실패시키는 대신 범위 안으로 끌어당긴다.
    @field_validator("intensity", mode="before")
    @classmethod
    def _clamp_intensity(cls, value: object) -> object:
        return _clamp(value, 1, 5)

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, value: object) -> object:
        return _clamp(value, 0.0, 1.0)

    @property
    def tags(self) -> list[str]:
        """검색 힌트로 쓸 감정 태그."""
        return [self.primary, *self.secondary]


class ExtractedEvent(BaseModel):

    summary: str = Field(description="사건을 한 줄로. 사용자가 말한 사실만")
    people: list[str] = Field(
        description="등장한 사람. 사용자가 부른 호칭 그대로. 없으면 빈 배열"
    )
    place: str | None = Field(default=None, description="장소. 언급이 없으면 null")
    when_hint: str | None = Field(
        default=None, description="'어제', '지난주' 같은 시간 표현 그대로. 날짜로 바꾸지 않는다"
    )


class ConversationState(BaseModel):
    events: list[ExtractedEvent] = Field(
        description="대화에 나온 사건들. 사건이 없으면 빈 배열"
    )
    emotion: EmotionReading
    topics: list[str] = Field(description="검색에 쓸 핵심어 2~5개")
    situation_clear: bool = Field(
        description=(
            "무슨 일이 있었는지 그림이 그려질 만큼 구체적이면 true. "
            "'힘들었어' 정도로 사건을 알 수 없으면 false"
        )
    )
    unclear_point: str | None = Field(
        description=(
            "아직 모르겠는 것 딱 하나. 이게 있으면 상담사가 그걸 물어본다. "
            "더 물을 게 없으면 null. 억지로 만들지 않는다"
        )
    )
    wants_closure: bool = Field(
        description=(
            "대화를 접으려는 신호가 있으면 true. 세 가지 중 하나면 true다. "
            "(1) 마음이 나아졌다고 말한다 — '좀 낫네요', '후련해요', '정리됐어요' "
            "(2) 고마움이나 작별을 말한다 — '고마워요', '이만 자야겠어요' "
            "(3) 그만하자고 한다 — '그만할래요', '오늘은 여기까지' "
            "새로운 이야기를 꺼내거나 되묻고 있으면 false"
        )
    )

    @property
    def entities(self) -> list[str]:
        names: list[str] = []
        for event in self.events:
            names.extend(event.people)
            if event.place:
                names.append(event.place)
        return list(dict.fromkeys(names))


class CounselTurn(BaseModel):

    role: Literal["user", "assistant"]
    content: str
    stage: str | None = None


class CounselRequest(BaseModel):
    user_id: str
    message: str = Field(min_length=1, max_length=2000)
    counsel_id: str | None = None
    memory_scope: MemoryScope = Field(default_factory=MemoryScope)


ClosingKind = Literal["emotion_card", "action_task"]


class CounselDraft(BaseModel):
    reply: str = Field(
        description="이번에 할 말. 공감하거나 짧게 반응한다. 2~3문장을 넘기지 않는다"
    )
    question: str | None = Field(
        description="이번에 물을 것 하나. 두 개 이상 묻지 않는다. 물을 게 없으면 null"
    )
    summary: str | None = Field(
        description="지금까지 나눈 이야기의 정리. 정리 단계가 아니면 반드시 null"
    )
    suggestion: str | None = Field(
        description=(
            "지금 마음에 도움이 될 것 하나. 행동이거나 음악이거나 둘 중 하나만. "
            "제안 단계가 아니면 반드시 null"
        )
    )
    suggestion_kind: Literal["action", "music"] | None = Field(
        description=(
            "suggestion이 무엇인지. 몸으로 하는 것이면 'action', "
            "들을 음악이면 'music'. suggestion이 null이면 null"
        )
    )
    closing_kind: ClosingKind | None = Field(
        default=None,
        description=(
            "마무리 단계에서 어떻게 끝낼지 고른 것. 마무리가 아니면 null. "
            "'emotion_card'면 summary만 채우고 suggestion은 null, "
            "'action_task'면 suggestion만 채우고 summary는 null"
        ),
    )


class CounselTrace(BaseModel):

    trace_id: str
    model: str
    latency_ms: int
    result_code: ResultCode
    stage: str | None = None  # 이번 턴의 대화 단계
    knowledge_count: int = 0  # 상담 지식 조각 수
    ontology_count: int = 0  # 개인 온톨로지 관계 수
    # 프롬프트에 실제로 들어간 일기 수와 그중 최상위 관련도.
    diary_count: int = 0
    diary_top_score: float | None = None
    # 임계값에 걸러지기 **전** 후보 최고점. 임계값(DIARY_*)을 실측으로 옮기기
    # 위한 관측값이다. 참조에 성공한 턴만 봐서는 기준을 낮출지 알 수 없다 —
    # 아깝게 떨어진 턴이 0.67인지 0.05인지가 판단 재료다.
    diary_top_candidate: float | None = None
    event_count: int = 0
    emotion: str | None = None  # 대표 감정 라벨만. 근거 문장은 남기지 않는다
    guardrail_hits: list[str] = Field(default_factory=list)
    stage_ms: dict[str, int] = Field(default_factory=dict)  # 단계별 소요 시간
    error_detail: str | None = None  # 실패 사유. 사용자 원문은 넣지 않는다


class CounselEvidenceRef(BaseModel):
    """이번 답변이 참고한 일기 한 건 (H-02).

    화면에 "8월 5일 일기를 참고했어요"로 보여준다. 상담사가 과거를 언급했을 때
    그게 어디서 왔는지 사용자가 확인할 수 있어야 한다.

    요약도 본문도 싣지 않는다. 어느 날 일기인지만 알면 되고, 내용을 다시
    화면에 펼치면 상담 답변 옆에 일기가 통째로 붙는 꼴이 된다.
    """

    session_id: str
    diary_date: date


class CounselReply(BaseModel):

    counsel_id: str
    message: str  # 화면에 그대로 출력할 조립된 답변
    sections: CounselDraft | None = None  # 위기·폴백 응답에서는 None
    state: ConversationState | None = None  # 이번 턴에서 구조화한 사건·감정
    stage: CounselStage | None = None  # 이번 턴의 대화 단계
    safety_level: SafetyLevel
    safety_notice: str | None = None  # 위기·주의 시 함께 보여줄 안내
    trace: CounselTrace
    # 비어 있으면 이번 답변은 과거 기록을 참고하지 않은 것이다.
    evidences: list[CounselEvidenceRef] = Field(default_factory=list)


class CounselSessionSummary(BaseModel):
    """지난 상담 하나를 목록에 한 줄로 보여주기 위한 요약.

    대화 내용은 담지 않는다. 목록을 그리자고 지난 상담 스무 개의 본문을 전부
    내려받을 이유가 없고, 그러면 화면에 쓰지도 않을 상담 기록이 클라이언트에
    쌓인다.
    """

    counsel_id: str
    title: str  # 첫 사용자 발화에서 만든다. 저장된 title 이 있으면 그걸 쓴다
    last_active_at: datetime
    turn_count: int
    safety_level: SafetyLevel
    is_crisis: bool


class CounselHistoryTurn(BaseModel):
    """지난 상담을 다시 열었을 때 화면에 그릴 한 줄.

    `evidences`가 붙는 이유는 H-02다. "8월 11일 일기를 참고했어요"가 새로고침
    한 번에 사라지면, 상담사가 과거를 어떻게 알았는지 확인할 방법이 없어진다.
    """

    role: Literal["user", "assistant"]
    content: str
    stage: str | None = None
    evidences: list[CounselEvidenceRef] = Field(default_factory=list)


class CounselHistory(BaseModel):
    counsel_id: str
    turns: list[CounselHistoryTurn] = Field(default_factory=list)


def _clamp(value: object, low: float, high: float) -> object:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    return type(value)(max(low, min(high, value)))
