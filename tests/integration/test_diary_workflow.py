import pytest

from backend.agents.diary_chatbot.models import (
    ChatbotTurnResult,
    EventCandidate,
    Evidence,
    InformationCoverage,
    WorkflowStage,
)
from backend.orchestration.diary_workflow import DiaryWorkflowState


def turn(*, sufficient: bool, questions: list[str]) -> ChatbotTurnResult:
    return ChatbotTurnResult(
        reaction="확인했어요.",
        action_text="",
        events=[EventCandidate(event="산책", evidence=[Evidence(input_id="text-1")])],
        coverage=InformationCoverage(
            has_person=sufficient, has_location=sufficient, has_emotion=sufficient,
            sufficient=sufficient, missing_fields=[] if sufficient else ["time", "emotion"],
        ),
        follow_up_questions=questions,
    )


def test_each_unanswered_field_can_receive_a_question() -> None:
    state = DiaryWorkflowState("session-1")
    for field_name, question in (
        ("person", "누구와 함께였나요?"),
        ("location", "어디였나요?"),
        ("emotion", "기분은 어땠나요?"),
    ):
        result = turn(sufficient=False, questions=[question])
        result.coverage.missing_fields = [field_name]
        assert state.apply_turn(result) is WorkflowStage.NEEDS_CLARIFICATION
    assert state.question_count == 3
    # 세 번째 질문에 답할 턴까지 받은 뒤 더 묻지 않고 확인 단계로 이동한다.
    assert state.apply_turn(turn(sufficient=False, questions=[])) \
        is WorkflowStage.AWAITING_SUMMARY_CONFIRMATION
    assert state.question_count == 3


def test_same_missing_field_can_be_asked_until_confirmed() -> None:
    state = DiaryWorkflowState("session-fields")
    first = turn(sufficient=False, questions=["기분은 어땠나요?"])
    first.coverage.missing_fields = ["emotion"]
    assert state.apply_turn(first) is WorkflowStage.NEEDS_CLARIFICATION
    assert state.asked_fields == {"emotion"}

    repeated = turn(sufficient=False, questions=["기분은 어땠나요?"])
    repeated.coverage.missing_fields = ["emotion"]
    assert state.apply_turn(repeated) is WorkflowStage.NEEDS_CLARIFICATION
    assert state.question_count == 2


def test_user_can_skip_current_missing_field() -> None:
    state = DiaryWorkflowState("session-skip")
    result = turn(sufficient=False, questions=["기분은 어땠나요?"])
    result.coverage.missing_fields = ["emotion"]
    state.apply_turn(result)

    assert state.skip_current_question(["emotion"]) is None
    assert state.skipped_fields == {"emotion"}
    assert state.stage is WorkflowStage.AWAITING_SUMMARY_CONFIRMATION


def test_render_requires_approval() -> None:
    state = DiaryWorkflowState("session-1")
    with pytest.raises(PermissionError):
        state.begin_render()
    state.apply_turn(turn(sufficient=True, questions=[]))
    state.confirm_summary(correct=True)
    state.choose_more_content(wants_more=False)
    state.mark_drafted()
    state.approve()
    state.begin_render()
    assert state.stage is WorkflowStage.RENDERING


def test_summary_review_supports_correction_and_optional_content() -> None:
    state = DiaryWorkflowState("session-review")
    state.apply_turn(turn(sufficient=True, questions=[]))
    assert state.confirm_summary(correct=False) is WorkflowStage.AWAITING_CORRECTION
    assert state.finish_review_input(correction=True) is WorkflowStage.AWAITING_SUMMARY_CONFIRMATION
    assert state.confirm_summary(correct=True) is WorkflowStage.AWAITING_MORE_CONTENT
    assert state.choose_more_content(wants_more=True) is WorkflowStage.ADDING_MORE_CONTENT
    assert state.finish_review_input(correction=False) is WorkflowStage.READY_TO_GENERATE
