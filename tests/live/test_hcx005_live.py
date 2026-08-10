import json
import os

import pytest

from backend.agents.diary_chatbot.hcx import Hcx005MultimodalChatAgent
from backend.agents.diary_chatbot.models import MultimodalContext
from backend.config import load_config

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_LLM_TESTS") != "1",
        reason="paid CLOVA Studio call; set RUN_LIVE_LLM_TESTS=1 explicitly",
    ),
]


@pytest.mark.anyio
async def test_live_hcx005_cannot_confirm_unwritten_emotion() -> None:
    config = load_config()
    if not config["llm"]["api_key"]:
        pytest.fail("CLOVA_STUDIO_API_KEY is required for live tests")
    agent = Hcx005MultimodalChatAgent(config)
    result = await agent.interpret(MultimodalContext(
        session_id="live-policy-test",
        text_inputs={"text-1": "친구랑 회사 근처에서 점심 먹고 산책했다"},
    ))

    print("\n" + "="*50)
    print("[HCX-005 라이브 응답 + 백엔드 후처리 최종 결과]")
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    print("="*50 + "\n")

    assert result.coverage.has_emotion is False
    assert result.coverage.missing_fields == ["emotion"]
    assert len(result.follow_up_questions) == 1
    assert isinstance(result.follow_up_questions[0], str)
    assert len(result.follow_up_questions[0]) > 0
