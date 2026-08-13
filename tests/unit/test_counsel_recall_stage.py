"""회상 단계 — 물어본 것에 답하고 되묻지 않는다.

"국밥 먹었던 거 기억나?"에 상담 흐름을 태우면 "어떤 계기로 드셨나요?"가
따라붙는다. 기억나지 않아서 물은 사람에게 기억을 요구하는 말이고, 이 기능이
있는 이유를 그대로 뒤집는다.

그래서 회상은 상담 단계가 아니라 조회 단계로 따로 뺐다. 판정은 구조화
LLM이 하고(`ConversationState.intent`), 질문이 나가지 않는 것은 코드가
보장한다 — 프롬프트만으로는 지시를 어길 때 막을 방법이 없다.
"""

from __future__ import annotations

import pytest

from backend.agents.counsel_chatbot.prompts import _STAGE_GUIDE, build_stage_guide
from backend.agents.counsel_chatbot.schemas import (
    ConversationState,
    CounselDraft,
    CounselStage,
    CounselTurn,
    EmotionReading,
    ExtractedEvent,
)
from backend.orchestration.counsel_flow import (
    _STAGE_ALLOWED,
    _STAGE_REQUIRED,
    _decide_stage,
    _enforce_stage,
    _stage_gaps,
)


def _state(**overrides: object) -> ConversationState:
    fields: dict[str, object] = {
        "events": [
            ExtractedEvent(summary="국밥을 먹었다", people=[], place=None, when_hint="지난번")
        ],
        "emotion": EmotionReading(
            primary="무덤덤", secondary=[], intensity=2, confidence=0.5, evidence=""
        ),
        "topics": ["국밥"],
        "situation_clear": False,
        "unclear_point": "어떤 국밥이었는지",
        "intent": "recall",
        "wants_closure": False,
    }
    fields.update(overrides)
    return ConversationState(**fields)  # type: ignore[arg-type]


def _draft(**overrides: object) -> CounselDraft:
    fields: dict[str, object] = {
        "reply": "이틀 연속 국밥을 드셨네요.",
        "question": "그날 어떤 국밥이었는지 기억나세요?",
        "summary": "국밥을 두 번 드셨습니다",
        "suggestion": "따뜻한 국물 한 그릇 어떠세요",
        "suggestion_kind": "action",
        "closing_kind": None,
    }
    fields.update(overrides)
    return CounselDraft(**fields)  # type: ignore[arg-type]


# --- 라우팅 -------------------------------------------------------------------


def test_recall_intent_routes_to_the_recall_stage() -> None:
    assert _decide_stage([], _state()) is CounselStage.RECALL


def test_recall_wins_over_closure() -> None:
    """"그날 얘기해주고 이만 잘게"처럼 섞여 오면 물어본 것부터 답한다."""
    assert _decide_stage([], _state(wants_closure=True)) is CounselStage.RECALL


def test_normal_intent_never_reaches_recall() -> None:
    """감정 대화가 회상으로 새면 털어놓는 사람에게 기록만 읽어주게 된다."""
    history = [
        CounselTurn(role="user", content="요즘 힘들어요"),
        CounselTurn(role="assistant", content="그러셨군요", stage="opening"),
    ]
    stage = _decide_stage(history, _state(intent="normal"))

    assert stage is not CounselStage.RECALL


def test_missing_state_never_reaches_recall() -> None:
    """구조화가 실패하면 intent 를 모른다. 모를 때는 상담 쪽으로 둔다."""
    assert _decide_stage([], None) is not CounselStage.RECALL


def test_intent_defaults_to_normal() -> None:
    """모델이 필드를 빠뜨려도 회상으로 새면 안 된다."""
    assert _state().model_copy(update={"intent": "normal"}).intent == "normal"
    built = ConversationState(
        events=[],
        emotion=EmotionReading(
            primary="무덤덤", secondary=[], intensity=1, confidence=0.3, evidence=""
        ),
        topics=[],
        situation_clear=False,
        unclear_point=None,
        wants_closure=False,
    )
    assert built.intent == "normal"


# --- 질문이 나가지 않는다 -------------------------------------------------------


def test_recall_strips_every_field_but_reply() -> None:
    """모델이 다 채워 와도 reply 하나만 남는다."""
    stripped = _enforce_stage(_draft(), CounselStage.RECALL, "t-1")

    assert stripped.reply == "이틀 연속 국밥을 드셨네요."
    assert stripped.question is None
    assert stripped.summary is None
    assert stripped.suggestion is None
    assert stripped.suggestion_kind is None
    assert stripped.closing_kind is None


def test_recall_does_not_resurrect_suggestion_kind() -> None:
    """일반 경로는 kind 가 비면 'action'으로 채워 넣는다. 회상에는 그 여지가 없다."""
    stripped = _enforce_stage(
        _draft(suggestion="국물 한 그릇", suggestion_kind=None),
        CounselStage.RECALL,
        "t-1",
    )

    assert stripped.suggestion is None
    assert stripped.suggestion_kind is None


def test_a_clean_recall_draft_is_returned_untouched() -> None:
    clean = CounselDraft(
        reply="그날은 동료분들과 드셨어요.",
        question=None, summary=None, suggestion=None, suggestion_kind=None,
    )

    assert _enforce_stage(clean, CounselStage.RECALL, "t-1") is clean


# --- 재생성이 질문을 다시 붙이지 않는다 -------------------------------------------


def test_recall_never_reports_a_missing_question() -> None:
    """여기가 기존 문제의 핵심이었다.

    `unclear_point`가 있으면 exploring 에서 question 을 요구한다. 회상에도
    그게 걸리면 "질문이 비었다"고 재생성이 돌아 기어이 질문이 붙는다.
    구조화는 회상 메시지에도 '아직 모르는 것'을 곧잘 만들어 낸다.
    """
    gaps = _stage_gaps(
        CounselDraft(
            reply="그날은 혼자 드셨어요.",
            question=None, summary=None, suggestion=None, suggestion_kind=None,
        ),
        CounselStage.RECALL,
        _state(unclear_point="어떤 국밥이었는지"),
    )

    assert gaps == []


def test_exploring_still_asks_when_something_is_unclear() -> None:
    """회상 예외를 넣느라 원래 동작이 사라지면 안 된다."""
    gaps = _stage_gaps(
        CounselDraft(
            reply="그러셨군요.",
            question=None, summary=None, suggestion=None, suggestion_kind=None,
        ),
        CounselStage.EXPLORING,
        _state(intent="normal", unclear_point="무엇이 가장 부담이었는지"),
    )

    assert "missing_question" in gaps


# --- 표가 빠짐없이 채워져 있는지 -------------------------------------------------


@pytest.mark.parametrize("table", [_STAGE_ALLOWED, _STAGE_REQUIRED, _STAGE_GUIDE])
def test_every_stage_is_mapped(table: dict) -> None:
    """단계를 추가하면 세 표를 다 채워야 한다. 빠지면 KeyError 로 그 턴이 죽는다."""
    assert {stage.value for stage in CounselStage} <= {
        stage.value for stage in table
    }


def test_recall_allows_no_optional_field() -> None:
    assert _STAGE_ALLOWED[CounselStage.RECALL] == frozenset()
    assert _STAGE_REQUIRED[CounselStage.RECALL] == frozenset()


def test_recall_guide_forbids_asking_back() -> None:
    guide = build_stage_guide(CounselStage.RECALL)

    assert "반드시 null" in guide
    assert "되묻지 않습니다" in guide
    assert "확인 가능한 기록이 없어요" in guide
