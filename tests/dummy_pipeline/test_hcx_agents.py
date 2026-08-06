import asyncio
import json

from backend.agents.diary_chatbot.hcx import Hcx005MultimodalChatAgent, Hcx007DiaryGenerationAgent
from backend.agents.diary_chatbot.models import MultimodalContext
from backend.services.llm import LLMResponse

CONFIG = {"llm": {"model_vision": "HCX-005", "model_reasoning": "HCX-007", "max_tokens": 1024}}


def test_hcx005_result_is_validated_as_structured_turn() -> None:
    async def fake_generate(request, config):
        assert request.model == "HCX-005"
        image_parts = request.messages[1].content
        assert image_parts[0]["imageUrl"]["url"] == "https://storage.example/photo.jpg"
        return LLMResponse(model="HCX-005", content=json.dumps({
            "reply": "산책 기록을 확인했어요.",
            "events": [{"event": "산책", "evidence": [{"input_id": "photo-1"}]}],
            "coverage": {"has_event": True, "has_time": False, "has_emotion": False,
                         "sufficient": False, "missing_fields": ["time", "emotion"]},
            "follow_up_questions": ["언제 산책했나요?", "기분은 어땠나요?"],
        }, ensure_ascii=False))

    agent = Hcx005MultimodalChatAgent(CONFIG, generate=fake_generate)
    result = asyncio.run(agent.interpret(MultimodalContext(
        session_id="session-1", image_urls={"photo-1": "https://storage.example/photo.jpg"}
    )))
    assert result.events[0].evidence[0].input_id == "photo-1"


def test_hcx007_result_is_validated_as_diary_draft() -> None:
    async def fake_generate(request, config):
        assert request.response_schema
        return LLMResponse(model="HCX-007", content=json.dumps({
            "title": "오늘의 산책",
            "paragraphs": ["첫 문단", "둘째 문단", "셋째 문단"],
            "summary": "공원을 산책했다.",
            "narration_script": "오늘은 공원을 천천히 걸었습니다.",
            "emotion_tags": ["평온"],
            "evidence_input_ids": ["photo-1"],
        }, ensure_ascii=False))

    agent = Hcx007DiaryGenerationAgent(CONFIG, generate=fake_generate)
    draft = asyncio.run(agent.generate([]))
    assert draft.model == "HCX-007"
