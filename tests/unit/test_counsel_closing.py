"""마무리 단계는 둘 중 하나로만 끝난다.

- emotion_card : 오늘을 한 줄로 되돌려준다 (감정은 이미 분석된 것을 쓴다)
- action_task  : 5분이면 되는 작은 행동 하나

둘 다 내보내면, 정리를 받고 가려던 사람에게 요약과 숙제가 함께 나간다.
모델은 프롬프트로 막아도 둘 다 채우므로 코드가 한쪽을 지운다.
"""

import pytest

from backend.agents.counsel_chatbot.schemas import CounselDraft, CounselStage
from backend.orchestration.counsel_flow import _enforce_stage, _stage_gaps


def draft(**overrides) -> CounselDraft:
    base = {
        "reply": "오늘 이야기 나눠줘서 고마워요.",
        "question": None,
        "summary": None,
        "suggestion": None,
        "suggestion_kind": None,
        "closing_kind": None,
    }
    base.update(overrides)
    return CounselDraft(**base)


def close(**overrides) -> CounselDraft:
    return _enforce_stage(draft(**overrides), CounselStage.CLOSING, "t-1")


# --- 1. 고른 쪽만 남는다 -----------------------------------------------------


def test_emotion_card_drops_the_action() -> None:
    """카드를 골랐으면 제안은 지운다."""
    result = close(
        closing_kind="emotion_card",
        summary="하루 종일 쉴 틈이 없었네요.",
        suggestion="따뜻한 차 한 잔 어때요",
        suggestion_kind="action",
    )

    assert result.closing_kind == "emotion_card"
    assert result.summary == "하루 종일 쉴 틈이 없었네요."
    assert result.suggestion is None
    assert result.suggestion_kind is None
    assert _stage_gaps(result, CounselStage.CLOSING, None) == []


def test_action_task_drops_the_summary() -> None:
    result = close(
        closing_kind="action_task",
        summary="하루 종일 쉴 틈이 없었네요.",
        suggestion="따뜻한 차 한 잔 어때요",
        suggestion_kind="action",
    )

    assert result.closing_kind == "action_task"
    assert result.summary is None
    assert result.suggestion == "따뜻한 차 한 잔 어때요"
    assert _stage_gaps(result, CounselStage.CLOSING, None) == []


def test_music_is_not_a_closing(  ) -> None:
    """마무리에 음악을 권하면, 잘 자라는 인사 대신 재생목록을 내미는 꼴이 된다."""
    result = close(
        closing_kind="action_task",
        suggestion="가사 없는 잔잔한 피아노곡",
        suggestion_kind="music",
    )

    assert result.suggestion_kind == "action"


# --- 2. 안 골랐으면 채워진 쪽에서 읽어낸다 -----------------------------------


def test_kind_is_inferred_when_only_one_side_is_filled() -> None:
    """모델이 closing_kind 를 빠뜨려도 한쪽만 찼으면 의도가 분명하다."""
    card = close(summary="하루가 길었네요.")
    task = close(suggestion="일찍 누워보세요", suggestion_kind="action")

    assert card.closing_kind == "emotion_card"
    assert task.closing_kind == "action_task"


def test_both_filled_without_a_choice_is_sent_back() -> None:
    """코드가 임의로 하나를 고르면 모델 의도와 무관한 마무리가 나간다."""
    result = close(
        summary="하루가 길었네요.",
        suggestion="일찍 누워보세요",
        suggestion_kind="action",
    )

    assert result.closing_kind is None
    assert _stage_gaps(result, CounselStage.CLOSING, None) == ["missing_closing_kind"]


def test_nothing_filled_is_sent_back() -> None:
    result = close()

    assert _stage_gaps(result, CounselStage.CLOSING, None) == ["missing_closing_kind"]


# --- 3. 고른 쪽이 비었으면 다시 시킨다 ---------------------------------------


def test_card_without_a_summary_is_sent_back() -> None:
    result = close(closing_kind="emotion_card")

    assert _stage_gaps(result, CounselStage.CLOSING, None) == ["missing_closing_card"]


def test_task_without_a_suggestion_is_sent_back() -> None:
    result = close(closing_kind="action_task")

    assert _stage_gaps(result, CounselStage.CLOSING, None) == ["missing_closing_task"]


# --- 4. 다른 단계는 영향받지 않는다 -------------------------------------------


@pytest.mark.parametrize(
    "stage", [CounselStage.OPENING, CounselStage.EXPLORING, CounselStage.CARING]
)
def test_closing_kind_is_stripped_outside_the_closing_stage(
    stage: CounselStage,
) -> None:
    """마무리가 아닌 턴에 마무리 표시가 붙으면 화면이 카드를 그린다."""
    result = _enforce_stage(
        draft(closing_kind="emotion_card", summary="정리", suggestion=None),
        stage,
        "t-1",
    )

    assert result.closing_kind is None


def test_caring_still_allows_a_summary_and_a_suggestion_together() -> None:
    """정리 단계는 둘 다 낸다. 마무리 규칙이 여기까지 번지면 안 된다."""
    result = _enforce_stage(
        draft(
            summary="하루 종일 쉴 틈이 없었네요.",
            suggestion="가사 없는 피아노곡 어때요",
            suggestion_kind="music",
        ),
        CounselStage.CARING,
        "t-1",
    )

    assert result.summary
    assert result.suggestion
    assert result.suggestion_kind == "music"
    assert _stage_gaps(result, CounselStage.CARING, None) == []
