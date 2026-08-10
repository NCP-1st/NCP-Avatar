from typing import Protocol

from backend.agents.counsel_chatbot.schemas import CounselTurn
from backend.api.schemas import DiarySession, NormalizedInputItem


class DiaryRepository(Protocol):
    """Minimal persistence contract required by the diary pipeline."""

    sessions: dict[str, DiarySession]
    inputs: dict[str, list[NormalizedInputItem]]

    def clear(self) -> None: ...


class ConversationStore(Protocol):
    """상담 대화 이력 저장소.

    대화 이력을 클라이언트가 들고 다니지 않고 서버가 보관한다 — 클라이언트가
    보낸 이력을 그대로 믿으면 이력 위조로 안전 규칙을 우회할 수 있다.
    """

    async def load_turns(
        self,
        *,
        counsel_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[CounselTurn]:
        """최근 대화를 오래된 순으로 돌려준다.

        `user_id`가 맞지 않으면 빈 목록을 돌려줘야 한다. 남의 counsel_id를
        찍어서 대화를 읽어가는 걸 막는 건 저장소의 책임이다.
        """
        ...

    async def append_turn(
        self,
        *,
        counsel_id: str,
        user_id: str,
        turn: CounselTurn,
    ) -> None:
        """대화 한 줄을 덧붙인다. 세션이 없으면 만든다."""
        ...

    async def mark_crisis(self, *, counsel_id: str, user_id: str) -> None:
        """이 세션에 위기 표시를 남긴다. 한 번 켜지면 세션 내내 유지된다."""
        ...

    async def is_crisis(self, *, counsel_id: str, user_id: str) -> bool:
        """이 세션에서 위기가 한 번이라도 감지됐는지.

        사용자가 화제를 돌려도 행동·음악 제안 경로를 열지 않기 위해 본다.
        위기 뒤에 "그건 그렇고 오늘 점심 뭐 먹을까요"가 와도 평소처럼
        제안하고 넘어가면 안 된다.
        """
        ...
