import json

import pytest

from backend.agents.diary_chatbot.hcx import Hcx005MultimodalChatAgent
from backend.orchestration.diary_orchestrator import (
    DiaryOrchestrator,
    _append_summary_sentence,
)
from backend.agents.diary_chatbot.models import WorkflowStage
from tests.orchestration.sequenced import SequencedGenerate


def _turn_response(
    *,
    event: str,
    input_id: str,
    people: list[str] | None = None,
    location: str | None = None,
    emotions: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "events": [
                {
                    "event": event,
                    "people": people or [],
                    "location": location,
                    "emotions": [
                        {"label": emotion, "excerpt": emotion, "input_id": input_id}
                        for emotion in (emotions or [])
                    ],
                    "evidence": [{"input_id": input_id, "excerpt": event}],
                }
            ],
            # 아래 값은 신뢰하지 않고 sanitize가 원문/이벤트에서 다시 계산한다.
            "coverage": {
                "has_person": bool(people),
                "has_location": location is not None,
                "has_emotion": bool(emotions),
                "missing_fields": [],
                "sufficient": True,
            },
        },
        ensure_ascii=False,
    )


def _config() -> dict:
    return {
        "llm": {
            "model_vision": "test-hcx-005",
            "model_reasoning": "test-hcx-007",
            "max_tokens": 1024,
            "followup_timeout_seconds": 1.0,
        }
    }


def test_completed_image_description_does_not_get_double_ending() -> None:
    summary = _append_summary_sentence(
        "친구들과 집에서 치맥했어요.",
        "사진에서 확인한 내용은 치킨과 맥주가 놓여 있습니다.",
    )
    assert summary.endswith("놓여 있습니다.")
    assert "습니다예요" not in summary


@pytest.mark.anyio
async def test_loop_stops_when_required_information_is_sufficient() -> None:
    generate = SequencedGenerate(
        [
            _turn_response(event="밥을 먹었다", input_id="turn-1"),
            '{"reaction":"밥을 드셨군요.","question":"누구와 함께 먹었나요?"}',
            _turn_response(event="민수와 밥을 먹었다", input_id="turn-2", people=["민수"]),
            '{"reaction":"민수와 함께였군요.","question":"어디에서 먹었나요?"}',
            _turn_response(
                event="민수와 화양동에서 밥을 먹었고 좋았어",
                input_id="turn-3",
                people=["민수"],
                location="화양동",
                emotions=["좋았어"],
            ),
            '{"reaction":"좋은 식사 시간이었군요.","question":null}',
        ]
    )
    chat_agent = Hcx005MultimodalChatAgent(_config(), generate=generate)
    orchestrator = DiaryOrchestrator(chat_agent=chat_agent)
    state = orchestrator.start_session("session-loop")

    state = await orchestrator.handle_turn(state, message="밥을 먹었어")
    assert state.stage is WorkflowStage.NEEDS_CLARIFICATION
    assert state.questions_asked_count == 1
    assert state.latest_turn is not None
    assert state.latest_turn.follow_up_questions == ["누구와 함께 먹었나요?"]

    state = await orchestrator.handle_turn(state, message="민수와 함께였어")
    assert state.stage is WorkflowStage.NEEDS_CLARIFICATION
    assert state.questions_asked_count == 2
    assert state.latest_turn is not None
    assert state.latest_turn.follow_up_questions == ["어디에서 먹었나요?"]

    state = await orchestrator.handle_turn(state, message="화양동에서 먹었고 좋았어")
    assert state.stage is WorkflowStage.AWAITING_SUMMARY_CONFIRMATION
    assert state.questions_asked_count == 2
    assert state.latest_turn is not None
    assert state.latest_turn.coverage.sufficient is True
    assert generate.call_count == 6
    assert generate.remaining == 0


@pytest.mark.anyio
async def test_loop_accepts_answer_to_third_question_before_stopping() -> None:
    generate = SequencedGenerate(
        [
            _turn_response(event="기록 1", input_id="turn-1"),
            '{"reaction":"기록했어요.","question":"누구와 함께했나요?"}',
            _turn_response(event="기록 2", input_id="turn-2"),
            '{"reaction":"계속 기록하고 있어요.","question":"어디에서 있었나요?"}',
            _turn_response(event="기록 3", input_id="turn-3"),
            '{"reaction":"이야기를 잘 들었어요.","question":"그때 기분은 어땠나요?"}',
            _turn_response(
                event="친구들과 화양동에서 이야기했고 재밌었다",
                input_id="turn-4",
                people=["친구들"],
                location="화양동",
                emotions=["재밌었다"],
            ),
            '{"reaction":"재미있는 시간이었군요.","question":null}',
        ]
    )
    chat_agent = Hcx005MultimodalChatAgent(_config(), generate=generate)
    orchestrator = DiaryOrchestrator(chat_agent=chat_agent)
    state = orchestrator.start_session("session-limit")

    for index in range(1, 4):
        state = await orchestrator.handle_turn(state, message=f"기록 {index}")

    assert state.questions_asked_count == 3
    assert state.stage is WorkflowStage.NEEDS_CLARIFICATION
    assert state.latest_turn is not None
    assert state.latest_turn.coverage.sufficient is False
    assert generate.call_count == 6

    state = await orchestrator.handle_turn(
        state, message="친구들과 화양동에 있었고 재밌었다"
    )
    assert state.stage is WorkflowStage.AWAITING_SUMMARY_CONFIRMATION
    assert state.questions_asked_count == 3
    assert generate.call_count == 8
    assert generate.remaining == 0


@pytest.mark.anyio
async def test_confirmed_person_and_location_are_carried_into_next_turn() -> None:
    generate = SequencedGenerate([
        _turn_response(
            event="친구들과 화양동에서 치맥했다",
            input_id="turn-1",
            people=["친구들"],
            location="화양동",
        ),
        '{"reaction":"친구들과 좋은 시간을 보내셨군요.","question":"그때 기분은 어떠셨어요?"}',
        _turn_response(
            event="편한 친구들과 수다를 나눴다",
            input_id="turn-2",
            emotions=["재밌더라고"],
        ),
        '{"reaction":"편한 친구들과 즐거운 시간을 보내셨군요.","question":null}',
    ])
    orchestrator = DiaryOrchestrator(
        chat_agent=Hcx005MultimodalChatAgent(_config(), generate=generate)
    )
    state = orchestrator.start_session("session-carry-forward")

    state = await orchestrator.handle_turn(
        state, message="화양동에서 친구들이랑 치맥했어"
    )
    assert state.latest_turn is not None
    assert state.latest_turn.coverage.missing_fields == ["emotion"]

    state = await orchestrator.handle_turn(
        state, message="편한 애들이랑 수다를 많이 떠니까 재밌더라고"
    )
    assert state.latest_turn is not None
    assert state.latest_turn.coverage.sufficient is True
    assert state.latest_turn.coverage.missing_fields == []
    assert state.latest_turn.response.question is None
    assert state.stage is WorkflowStage.AWAITING_SUMMARY_CONFIRMATION
    assert state.review_summary == (
        "친구들과 화양동에서 치맥했다, 편한 친구들과 수다를 나눴다, "
        "이때 느낀 감정은 재밌더라고였어요."
    )
