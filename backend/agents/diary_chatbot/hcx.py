import json
from collections.abc import Awaitable, Callable
from typing import Any

from backend.agents.diary_chatbot.base import DiaryGenerationAgent, MultimodalChatAgent
from backend.agents.diary_chatbot.models import ChatbotTurnResult, DiaryDraft, MultimodalContext
from backend.services.llm import ChatMessage, LLMRequest, LLMResponse, generate_llm

GenerateFunction = Callable[[LLMRequest, dict[str, Any]], Awaitable[LLMResponse]]

INTERPRET_SYSTEM_PROMPT = """
당신은 Mediary의 멀티모달 일기 챗봇이다. 입력에 없는 사실을 추측하지 않는다.
사건, 시간, 인물, 장소, 행동, 감정을 추출하고 모든 사건에 근거 input_id를 연결한다.

[판단 지침]
- 감정(emotions)이나 장소(place) 정보가 누락된 경우, coverage.sufficient는 반드시 false로 설정하고 missing_fields에 해당 항목을 추가한다.
- coverage.sufficient가 false일 때만 부족한 정보를 묻는 질문을 follow_up_questions에 최대 3개 작성한다.
- 사건, 시간, 감정, 장소가 모두 파악되면 coverage.sufficient를 true로 설정한다.

JSON 외의 텍스트는 출력하지 않으며, 제공된 ChatbotTurnResult JSON 스키마를 정확히 따른다.
""".strip()

GENERATE_SYSTEM_PROMPT = """
누적된 사건과 근거만 사용해 한국어 일기를 작성한다. 3~7개 문단과 약 30초 나레이션 대본을 만든다.
과도한 감정 해석이나 근거 없는 인물·장소·시간을 추가하지 않는다.
""".strip()


class Hcx005MultimodalChatAgent(MultimodalChatAgent):
    def __init__(self, config: dict[str, Any], *, generate: GenerateFunction = generate_llm) -> None:
        self._config = config
        self._generate = generate

    async def interpret(self, context: MultimodalContext) -> ChatbotTurnResult:
        content: list[dict[str, Any]] = []
        for input_id, url in context.image_urls.items():
            content.append({"type": "image_url", "imageUrl": {"url": url}})
            content.append({"type": "text", "text": f"위 이미지의 input_id: {input_id}"})
        facts = {
            "session_id": context.session_id,
            "user_message": context.user_message,
            "text_inputs": context.text_inputs,
            "audio_transcripts": context.audio_transcripts,
            "output_schema": ChatbotTurnResult.model_json_schema(),
        }
        content.append({"type": "text", "text": json.dumps(facts, ensure_ascii=False)})
        response = await self._generate(
            LLMRequest(
                model=self._config["llm"]["model_vision"],
                messages=[
                    ChatMessage(role="system", content=INTERPRET_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=content),
                ],
                temperature=0.2,
                max_tokens=self._config["llm"]["max_tokens"],
            ),
            self._config,
        )
        result = ChatbotTurnResult.model_validate_json(_json_only(response.content))
        return result.model_copy(update={"model": response.model})


class Hcx007DiaryGenerationAgent(DiaryGenerationAgent):
    def __init__(self, config: dict[str, Any], *, generate: GenerateFunction = generate_llm) -> None:
        self._config = config
        self._generate = generate

    async def generate(self, turns: list[ChatbotTurnResult]) -> DiaryDraft:
        response = await self._generate(
            LLMRequest(
                model=self._config["llm"]["model_reasoning"],
                messages=[
                    ChatMessage(role="system", content=GENERATE_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=json.dumps(
                        [turn.model_dump() for turn in turns], ensure_ascii=False
                    )),
                ],
                response_schema=DiaryDraft.model_json_schema(),
                temperature=0.2,
                max_tokens=self._config["llm"]["max_tokens"],
            ),
            self._config,
        )
        draft = DiaryDraft.model_validate_json(_json_only(response.content))
        return draft.model_copy(update={"model": response.model})


def _json_only(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```json") and stripped.endswith("```"):
        return stripped[7:-3].strip()
    return stripped
