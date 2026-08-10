

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import ValidationError

from backend.agents.counsel_chatbot import prompts
from backend.agents.counsel_chatbot.schemas import (
    EMOTION_LABELS,
    NEUTRAL_EMOTION,
    ConversationState,
    CounselTurn,
)
from backend.services.llm import ChatMessage, LLMRequest, generate_llm

logger = logging.getLogger(__name__)

_MAX_TOKENS = 640
_MAX_SECONDARY = 2
_MAX_TOPICS = 5
_FALLBACK_CONFIDENCE = 0.2  # 라벨을 중립으로 떨어뜨렸을 때의 확신도 상한

_CLOSURE_PATTERN = re.compile(
    # 마음이 나아졌다
    r"(좀|조금|한결|훨씬)?\s*(낫네|낫다|나아졌|괜찮아졌|후련|시원|홀가분)"
    r"|정리(가|된|됐|가\s*좀\s*됐)"
    r"|(말|얘기|이야기)하(고|니|니까)\s*나(니|서)?\s*(좀|조금)?\s*(괜찮|낫|시원|가벼)"
    r"|마음이\s*(좀|조금|한결)?\s*(가벼|편해|놓)"
    # 고마움·작별
    r"|고마([워웠]|워요|웠어)|고맙(습니다|네요|다)|감사(해요|합니다|해)"
    r"|잘\s*자|안녕히|내일\s*(또|다시)|다음에\s*(또|다시)?\s*(얘기|올게|봐요)"
    r"|이만\s*(자|가|갈|할|줄일)|자야겠|자러\s*갈"
    # 그만하자
    r"|그만(할래|하자|둘래|할게|하죠)|여기까지|오늘은\s*(이만|여기)"
    r"|나중에\s*(얘기|말할|다시)"
)

_QUESTION_PATTERN = re.compile(
    r"[?？]|(까요|나요|ㄹ까|을까|런가요)\s*[.…!]*\s*$|어떡|어떻게\s*해"
)


class ContextAgent:
    """대화 → 사건 + 감정 상태."""

    def __init__(self, config: dict[str, Any], *, temperature: float = 0.1) -> None:
        self._config = config
        # Structured Outputs는 추론 모델에서만 동작한다 (services/llm/generate.py).
        self._model: str = config["llm"]["model_reasoning"]
        self._temperature = temperature  # 구조화는 흔들리지 않게 낮게

    async def structure(
        self,
        message: str,
        history: list[CounselTurn],
    ) -> ConversationState:
        user_prompt = prompts.build_context_prompt(message, history)
        response = await generate_llm(
            LLMRequest(
                model=self._model,
                messages=[
                    ChatMessage(role="system", content=prompts.CONTEXT_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=user_prompt),
                ],
                response_schema=ConversationState.model_json_schema(),
                temperature=self._temperature,
                max_tokens=_MAX_TOKENS,
            ),
            self._config,
        )

        try:
            state = ConversationState.model_validate_json(response.content)
        except ValidationError as exc:
            raise ValueError("대화 구조화 결과가 스키마를 만족하지 않습니다") from exc

        return _normalize(state, message)


def _normalize(state: ConversationState, message: str) -> ConversationState:

    emotion = state.emotion
    primary = emotion.primary.strip()
    confidence = emotion.confidence

    if primary not in EMOTION_LABELS:
        logger.warning("emotion label out of range: %s", primary[:20])
        primary = NEUTRAL_EMOTION
        confidence = min(confidence, _FALLBACK_CONFIDENCE)

    secondary = [
        label.strip()
        for label in dict.fromkeys(emotion.secondary)
        if label.strip() in EMOTION_LABELS and label.strip() != primary
    ][:_MAX_SECONDARY]

    topics = [topic.strip() for topic in dict.fromkeys(state.topics) if topic.strip()]

    return state.model_copy(
        update={
            "emotion": emotion.model_copy(
                update={
                    "primary": primary,
                    "secondary": secondary,
                    "confidence": confidence,
                    "evidence": _verify_evidence(emotion.evidence, message),
                }
            ),
            "topics": topics[:_MAX_TOPICS],
            "wants_closure": _detect_closure(state.wants_closure, message),
        }
    )


def _detect_closure(model_says: bool, message: str) -> bool:

    if _QUESTION_PATTERN.search(message):
        if model_says:
            logger.info("closure 취소 — 되묻는 중: %s", message[:30])
        return False

    if model_says:
        return True

    if _CLOSURE_PATTERN.search(message):
        logger.info("closure 감지(키워드) — 모델은 놓침: %s", message[:30])
        return True

    return False


def _verify_evidence(evidence: str, message: str) -> str:

    cleaned = evidence.strip().strip("\"'“”‘’ ")
    if len(cleaned) < 2:
        return ""
    if _squash(cleaned) in _squash(message):
        return cleaned

    logger.info("emotion evidence가 이번 메시지에 없어 버림: %s", cleaned[:30])
    return ""


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)
