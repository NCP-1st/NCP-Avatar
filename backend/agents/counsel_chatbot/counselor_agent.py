

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from backend.agents.counsel_chatbot import prompts
from backend.services.knowledge.base import (
    DiaryReference,
    KnowledgeSnippet,
    OntologyFact,
)
from backend.agents.counsel_chatbot.schemas import (
    ConversationState,
    CounselDraft,
    CounselStage,
    CounselTurn,
)
from backend.services.llm import ChatMessage, LLMRequest, generate_llm


class CounselorAgent:

    def __init__(self, config: dict[str, Any], *, temperature: float = 0.4) -> None:
        self._config = config
        self._model: str = config["llm"]["model_reasoning"]
        self._temperature = temperature

    @property
    def model(self) -> str:
        return self._model

    async def draft(
        self,
        *,
        message: str,
        stage: CounselStage,
        state: ConversationState | None,
        snippets: list[KnowledgeSnippet],
        facts: list[OntologyFact],
        history: list[CounselTurn],
        diary_refs: list[DiaryReference] | None = None,
        violations: list[str] | None = None,
    ) -> CounselDraft:
        system = prompts.COUNSELOR_SYSTEM_PROMPT + "\n\n" + prompts.build_stage_guide(stage)
        if violations:
            system += "\n\n" + prompts.build_reinforcement(violations)

        user_prompt = prompts.build_counselor_prompt(
            message,
            state,
            snippets,
            facts,
            history,
            diary_refs,
        )

        response = await generate_llm(
            LLMRequest(
                model=self._model,
                messages=[
                    ChatMessage(role="system", content=system),
                    ChatMessage(role="user", content=user_prompt),
                ],
                response_schema=CounselDraft.model_json_schema(),
                temperature=self._temperature,
                max_tokens=self._config["llm"]["max_tokens"],
            ),
            self._config,
        )

        try:
            return CounselDraft.model_validate_json(response.content)
        except ValidationError as exc:
            raise ValueError("상담 초안이 스키마를 만족하지 않습니다") from exc

