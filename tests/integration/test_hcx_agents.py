import asyncio
import json
import logging

import pytest
from backend.agents.diary_chatbot.hcx import Hcx005MultimodalChatAgent, Hcx007DiaryGenerationAgent
from backend.agents.diary_chatbot.models import (
    ChatbotTurnResult,
    EmotionMention,
    EventCandidate,
    Evidence,
    InformationCoverage,
    MultimodalContext,
    TurnResponse,
)
from backend.services.llm import LLMResponse
from tests.agents.mock_responses import TEXT_ONLY_LOCATION_MISSED

CONFIG = {"llm": {"model_vision": "HCX-005", "model_reasoning": "HCX-007", "max_tokens": 1024}}


@pytest.mark.parametrize(
    "reaction",
    [
        "그때 어떤 기분이었나요?",
    ],
)
def test_turn_response_rejects_question_inside_reaction(reaction: str) -> None:
    with pytest.raises(ValueError, match="reaction must not contain a question"):
        TurnResponse(reaction=reaction, question="기분을 알려주세요?")


def test_hcx005_result_is_validated_as_structured_turn() -> None:
    async def fake_generate(request, config):
        assert request.model == "HCX-005"
        assert "reaction" not in request.messages[1].content[-1]["text"]
        assert "question" not in request.messages[1].content[-1]["text"]
        image_parts = request.messages[1].content
        assert image_parts[0]["image_url"]["url"] == "https://storage.example/photo.jpg"
        hallucinated = json.dumps({
            "reaction": "산책 기록을 확인했어요.",
            "action_text": "LLM이 만든 문구",
            "events": [{"event": "산책", "people": ["친구"], "location": "공원",
                        "emotions": [{
                            "label": "행복했음", "excerpt": "행복했다", "input_id": "photo-1"
                        }],
                        "evidence": [{"input_id": "photo-1"}]}],
            "coverage": {"has_person": True, "has_location": True, "has_emotion": True,
                         "sufficient": True, "missing_fields": []},
            "image_observations": [{
                "input_id": "photo-1",
                "description": "공원에서 사람들이 산책하는 모습이 보인다.",
                "observed_facts": ["공원", "산책"],
                "related_event": "산책",
            }],
            "follow_up_questions": [],
        }, ensure_ascii=False)
        return LLMResponse(model="HCX-005", content=f"```json\n{hallucinated}\n```")

    agent = Hcx005MultimodalChatAgent(CONFIG, generate=fake_generate)
    result = asyncio.run(agent.interpret(MultimodalContext(
        session_id="session-1", image_urls={"photo-1": "https://storage.example/photo.jpg"}
    )))
    assert result.events[0].evidence[0].input_id == "photo-1"
    assert result.events[0].emotions == []
    assert result.image_observations[0].input_id == "photo-1"
    assert result.reaction.startswith("사진도 확인했어요.")
    assert result.coverage.sufficient is False
    assert result.coverage.missing_fields == ["location", "emotion"]
    assert result.follow_up_questions == ["어느 동에서 있었던 일인가요?"]


def test_hcx005_accepts_data_only_single_quoted_mapping() -> None:
    calls = 0

    async def fake_generate(request, config):
        nonlocal calls
        calls += 1
        if calls == 1:
            return LLMResponse(model="HCX-005", content=str({
                "events": [{
                    "event": "민수와 화양동에서 산책했다",
                    "people": ["민수"],
                    "location": "화양동",
                    "emotions": [{
                        "label": "즐거웠음", "excerpt": "즐거웠다", "input_id": "text-1"
                    }],
                    "evidence": [{"input_id": "text-1"}],
                }],
                "coverage": {
                    "has_person": True,
                    "has_location": True,
                    "has_emotion": True,
                    "sufficient": True,
                    "missing_fields": [],
                },
            }))
        return LLMResponse(
            model="HCX-005",
            content="{'reaction': '즐거운 산책이었군요.', 'question': None}",
        )

    agent = Hcx005MultimodalChatAgent(CONFIG, generate=fake_generate)
    result = asyncio.run(agent.interpret(MultimodalContext(
        session_id="single-quotes",
        text_inputs={"text-1": "민수와 화양동에서 산책했고 즐거웠다"},
    )))

    assert result.response.reaction == "즐거운 산책이었군요."
    assert result.response.question is None


def test_hcx005_normalizes_exact_legacy_emotion_string_without_retry() -> None:
    calls = 0

    async def fake_generate(request, config):
        nonlocal calls
        calls += 1
        if calls == 1:
            return LLMResponse(model="HCX-005", content=json.dumps({
                "events": [{
                    "event": "친구들과 수다를 나눴다",
                    "people": ["친구들"],
                    "location": "집 근처",
                    "emotions": ["재밌었어"],
                    "evidence": [{"input_id": "turn-2"}],
                }],
                "coverage": {
                    "has_person": True,
                    "has_location": True,
                    "has_emotion": True,
                    "sufficient": True,
                    "missing_fields": [],
                },
            }, ensure_ascii=False))
        return LLMResponse(
            model="HCX-005",
            content='{"reaction":"친구들과 즐거운 시간을 보내셨군요.","question":null}',
        )

    result = asyncio.run(Hcx005MultimodalChatAgent(CONFIG, generate=fake_generate).interpret(
        MultimodalContext(
            session_id="legacy-emotion",
            text_inputs={"turn-2": "오랜만에 친구들과 수다를 떠니 재밌었어"},
        )
    ))

    assert calls == 2
    assert result.events[0].emotions[0].excerpt == "재밌었어"
    assert result.events[0].emotions[0].input_id == "turn-2"
    assert result.coverage.has_emotion is True


def test_hcx005_normalizes_missing_evidence_without_repair_call() -> None:
    calls = 0

    async def fake_generate(request, config):
        nonlocal calls
        calls += 1
        if calls == 1:
            return LLMResponse(model="HCX-005", content=json.dumps({
                "reaction": "기록을 확인했어요.",
                "action_text": "",
                "events": [{
                    "event": "민수와 화양동에서 산책했고 좋았어",
                    "people": ["민수"],
                    "location": "화양동",
                    "emotions": [{
                        "label": "좋았음", "excerpt": "좋았어", "input_id": "text-1"
                    }],
                }],
                "coverage": {
                    "has_person": True,
                    "has_location": True,
                    "has_emotion": True,
                    "sufficient": True,
                    "missing_fields": [],
                },
                "follow_up_questions": [],
            }, ensure_ascii=False))

        return LLMResponse(
            model="HCX-005",
            content='{"reaction":"좋은 산책이었군요.","question":null}',
        )

    agent = Hcx005MultimodalChatAgent(CONFIG, generate=fake_generate)
    result = asyncio.run(agent.interpret(MultimodalContext(
        session_id="repair-evidence",
        text_inputs={"text-1": "민수와 화양동에서 좋았어"},
    )))

    assert calls == 2
    assert result.events[0].evidence[0].input_id == "text-1"
    assert result.coverage.sufficient is True


def test_hcx005_normalizes_missing_evidence_to_exact_current_turn() -> None:
    calls = 0

    async def fake_generate(request, config):
        nonlocal calls
        calls += 1
        if calls == 1:
            return LLMResponse(model="HCX-005", content=json.dumps({
                "events": [{
                    "event": "친구들과 수다를 나눴다",
                    "emotions": [{
                        "label": "재미있었음",
                        "excerpt": "재밌더라고",
                        "input_id": "turn-2",
                    }],
                }],
                "coverage": {
                    "has_person": False,
                    "has_location": False,
                    "has_emotion": True,
                    "sufficient": False,
                    "missing_fields": ["person", "location"],
                },
            }, ensure_ascii=False))
        return LLMResponse(
            model="HCX-005",
            content=(
                '{"reaction":"수다를 나누며 재미있는 시간을 보내셨군요.",'
                '"question":"누구와 함께 있었나요?"}'
            ),
        )

    message = "수다를 왕창 떠니까 재밌더라고"
    result = asyncio.run(Hcx005MultimodalChatAgent(CONFIG, generate=fake_generate).interpret(
        MultimodalContext(
            session_id="current-evidence",
            user_message=message,
            text_inputs={"turn-1": "친구들과 치맥했어", "turn-2": message},
        )
    ))

    assert calls == 2
    assert result.events[0].evidence[0].input_id == "turn-2"


def test_hcx005_infers_evidence_only_from_unique_matching_text() -> None:
    calls = 0

    async def always_missing_evidence(request, config):
        nonlocal calls
        calls += 1
        return LLMResponse(model="HCX-005", content=json.dumps({
            "reaction": "기록을 확인했어요.",
            "action_text": "",
            "events": [{"event": "식사했다"}],
            "coverage": {
                "has_person": False,
                "has_location": False,
                "has_emotion": False,
                "sufficient": False,
                "missing_fields": ["person", "location", "emotion"],
            },
            "follow_up_questions": [],
        }, ensure_ascii=False))

    agent = Hcx005MultimodalChatAgent(CONFIG, generate=always_missing_evidence)
    result = asyncio.run(agent.interpret(MultimodalContext(
            session_id="ambiguous-evidence",
            text_inputs={"text-1": "식사했다"},
            image_urls={"img-1": "https://storage.example/meal.jpg"},
        )))

    assert calls == 3
    assert result.events[0].evidence[0].input_id == "text-1"
    assert result.image_observations[0].description == "이미지 내용을 명확히 확인하지 못했습니다."
    assert result.image_clarity[0].unclear is True


def test_hcx007_result_is_validated_as_diary_draft() -> None:
    async def fake_generate(request, config):
        assert request.response_schema
        return LLMResponse(model="HCX-007", content=json.dumps({
            "title": "오늘의 산책",
            "paragraphs": ["첫 문단", "둘째 문단", "셋째 문단"],
            "summary": "공원을 산책했다.",
            "content": "오늘은 공원을 천천히 걸었습니다.",
            "emotion_tags": ["좋았다", "만족스러움"],
            "evidence_input_ids": ["photo-1"],
        }, ensure_ascii=False))

    agent = Hcx007DiaryGenerationAgent(CONFIG, generate=fake_generate)
    turns = [ChatbotTurnResult(
        reaction="좋은 시간이었네요.",
        action_text="이대로 일기를 작성해 드릴까요?",
        events=[EventCandidate(
            event="산책",
            people=["친구"],
            location="공원",
            emotions=[EmotionMention(label="좋았다", excerpt="좋았다", input_id="text-1")],
            evidence=[Evidence(input_id="text-1")],
        )],
        coverage=InformationCoverage(
            has_person=True, has_location=True, has_emotion=True,
            sufficient=True, missing_fields=[],
        ),
    )]
    draft = asyncio.run(agent.generate(turns))
    assert draft.model == "HCX-007"
    assert draft.emotion_tags == ["좋았다"]


def test_natural_question_changes_wording_only_not_selected_field() -> None:
    calls = 0

    async def fake_generate(request, config):
        nonlocal calls
        calls += 1
        if calls == 1:
            return LLMResponse(model="HCX-005", content=json.dumps({
                "reaction": "기록을 확인했어요.",
                "action_text": "LLM 임의 문구",
                "events": [{"event": "산책", "evidence": [{"input_id": "text-1"}]}],
                "coverage": {"has_person": True, "has_location": True, "has_emotion": True,
                             "sufficient": True, "missing_fields": []},
                "follow_up_questions": [],
            }, ensure_ascii=False))
        assert "함께 있었던 사람" in request.messages[1].content
        assert "있었던 장소" not in request.messages[1].content
        return LLMResponse(
            model="HCX-005",
            content=(
                '{"reaction":"산책을 다녀오셨군요.",'
                '"question":"혹시 그 자리에 누구와 함께 있었나요?"}'
            ),
        )

    agent = Hcx005MultimodalChatAgent(CONFIG, generate=fake_generate)
    result = asyncio.run(agent.interpret(MultimodalContext(
        session_id="session-1", text_inputs={"text-1": "산책했다"}
    )))
    assert result.coverage.missing_fields == ["person", "location", "emotion"]
    assert result.action_text == "부족한 정보를 확인할게요."
    assert result.follow_up_questions == ["혹시 그 자리에 누구와 함께 있었나요?"]


def test_response_composer_is_anchored_to_current_additional_input() -> None:
    calls = 0

    async def fake_generate(request, config):
        nonlocal calls
        calls += 1
        if calls == 1:
            return LLMResponse(model="HCX-005", content=json.dumps({
                "events": [{
                    "event": "후식 배달이 잘못 와서 아쉬웠다",
                    "emotions": [{
                        "label": "아쉬움", "excerpt": "아쉬웠어", "input_id": "turn-2"
                    }],
                    "evidence": [{"input_id": "turn-2"}],
                }],
                "coverage": {
                    "has_person": False, "has_location": False, "has_emotion": True,
                    "sufficient": False, "missing_fields": ["person", "location"],
                },
            }, ensure_ascii=False))
        composer_prompt = request.messages[1].content
        assert "치맥하고 후식으로 아이스크림도 시켜먹었어" in composer_prompt
        assert "후식 배달이 잘못 와서 아쉬웠다" in composer_prompt
        assert "신나게 웃고 떠들었다" not in composer_prompt
        return LLMResponse(
            model="HCX-005",
            content='{"reaction":"배달이 잘못 와서 아쉬우셨겠어요.","question":null}',
        )

    message = "치맥하고 후식으로 아이스크림도 시켜먹었어 근데 배달이 잘못와서 아쉬웠어"
    prior = EventCandidate(
        event="친구들과 신나게 웃고 떠들었다",
        people=["친구들"],
        location="집",
        evidence=[Evidence(input_id="turn-1")],
    )
    result = asyncio.run(Hcx005MultimodalChatAgent(CONFIG, generate=fake_generate).interpret(
        MultimodalContext(
            session_id="additional-content",
            user_message=message,
            text_inputs={"turn-2": message},
            prior_events=[prior],
        )
    ))

    assert calls == 2
    assert result.response.reaction == "배달이 잘못 와서 아쉬우셨겠어요."


def test_interpret_failure_log_does_not_store_exception_message(caplog) -> None:
    async def failing_generate(request, config):
        raise ValueError("민감한 사용자 원문")

    agent = Hcx005MultimodalChatAgent(CONFIG, generate=failing_generate)
    with caplog.at_level(logging.WARNING, logger="mediary.diary_chatbot"):
        with pytest.raises(ValueError):
            asyncio.run(agent.interpret(MultimodalContext(
                session_id="trace-only", text_inputs={"text-1": "민감한 사용자 원문"}
            )))

    record = caplog.records[-1]
    assert record.getMessage() == "interpret_failed"
    assert record.error_type == "ValueError"
    assert not hasattr(record, "error")
    assert "민감한 사용자 원문" not in caplog.text


def test_explicit_location_miss_is_flagged_without_guessing(caplog) -> None:
    calls = 0

    async def scripted_generate(request, config):
        nonlocal calls
        calls += 1
        if calls == 1:
            return LLMResponse(model="HCX-005", content=TEXT_ONLY_LOCATION_MISSED)
        return LLMResponse(model="HCX-005", content="그 자리에 누구랑 함께 있었나요?")

    agent = Hcx005MultimodalChatAgent(CONFIG, generate=scripted_generate)
    with caplog.at_level(logging.INFO, logger="mediary.diary_chatbot"):
        result = asyncio.run(agent.interpret(MultimodalContext(
            session_id="location-miss",
            text_inputs={"text-1": "건대에서 먹은건데 아주 맛있었어"},
            image_urls={"img-1": "https://storage.example/food.jpg"},
        )))

    assert result.events[0].location is None
    assert result.events[0].evidence[0].input_id == "text-1"
    assert result.coverage.has_location is False
    assert "location" in result.coverage.missing_fields
    assert result.coverage.sufficient is False
    warning = next(record for record in caplog.records if record.getMessage() == "possible_location_missed")
    assert warning.trace_id == "location-miss"
    assert not hasattr(warning, "excerpt")
