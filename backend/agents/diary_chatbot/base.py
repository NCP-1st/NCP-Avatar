from abc import ABC, abstractmethod

from backend.agents.diary_chatbot.models import ChatbotTurnResult, DiaryDraft, MultimodalContext


class MultimodalChatAgent(ABC):
    @abstractmethod
    async def interpret(self, context: MultimodalContext) -> ChatbotTurnResult: ...


class DiaryGenerationAgent(ABC):
    @abstractmethod
    async def generate(self, turns: list[ChatbotTurnResult]) -> DiaryDraft: ...
