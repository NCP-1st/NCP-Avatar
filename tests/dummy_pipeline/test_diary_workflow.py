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
        reply="확인했어요.",
        events=[EventCandidate(event="산책", evidence=[Evidence(input_id="text-1")])],
        coverage=InformationCoverage(
            has_event=True, has_time=sufficient, has_emotion=sufficient,
            sufficient=sufficient, missing_fields=[] if sufficient else ["time", "emotion"],
        ),
        follow_up_questions=questions,
    )


def test_questions_are_capped_at_three_then_generation_is_allowed() -> None:
    state = DiaryWorkflowState("session-1")
    assert state.apply_turn(turn(sufficient=False, questions=["언제였나요?", "기분은 어땠나요?"])) \
        is WorkflowStage.NEEDS_CLARIFICATION
    assert state.apply_turn(turn(sufficient=False, questions=["누구와 함께였나요?", "추가 질문"])) \
        is WorkflowStage.READY_TO_GENERATE
    assert state.question_count == 3


def test_render_requires_approval() -> None:
    state = DiaryWorkflowState("session-1")
    with pytest.raises(PermissionError):
        state.begin_render()
    state.apply_turn(turn(sufficient=True, questions=[]))
    state.mark_drafted()
    state.approve()
    state.begin_render()
    assert state.stage is WorkflowStage.RENDERING
