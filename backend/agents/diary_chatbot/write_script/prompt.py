"""대본 작성 에이전트 프롬프트."""

from __future__ import annotations

import json

from backend.agents.diary_chatbot.write_script.schemas import WriteScriptInput
from backend.services.llm import ChatMessage


_SYSTEM_PROMPT = """당신은 완성된 일기를 영상용 나레이션으로 다듬는 작가입니다.

규칙:
- 10대 학생처럼 장난기 있는 어감으로 대본을 작성해줘.
- 완성된 일기에 없는 사실을 추가하거나 과장하지 않습니다.
- 일기의 핵심 사건과 감정을 유지합니다.
- 한국어로 자연스럽게 소리 내어 읽기 좋은 한 편의 대본을 작성합니다.
- 목표 재생 시간을 고려해 간결하게 작성합니다.
- emotion은 중립, 슬픔, 기쁨, 분노 중 대표 감정 하나를 선택합니다.
- narration_text와 emotion만 요청된 구조화 스키마에 맞게 반환합니다.
"""


def build_script_messages(data: WriteScriptInput) -> list[ChatMessage]:
    """검증된 입력으로 대본 생성용 메시지를 만든다."""
    payload = data.model_dump(mode="json")
    return [
        ChatMessage(role="system", content=_SYSTEM_PROMPT),
        ChatMessage(
            role="user",
            content=(
                "다음 일기를 나레이션 대본으로 작성하세요.\n"
                + json.dumps(payload, ensure_ascii=False, indent=2)
            ),
        ),
    ]
