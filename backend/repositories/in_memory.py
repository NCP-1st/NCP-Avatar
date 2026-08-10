import asyncio
from collections import defaultdict

from backend.agents.counsel_chatbot.schemas import CounselTurn
from backend.api.schemas import DiarySession, NormalizedInputItem


class InMemoryDiaryRepository:
    """Local development repository; replace with the MySQL implementation."""

    def __init__(self) -> None:
        self.sessions: dict[str, DiarySession] = {}
        self.inputs: dict[str, list[NormalizedInputItem]] = {}

    def clear(self) -> None:
        self.sessions.clear()
        self.inputs.clear()


class InMemoryConversationStore:
    """대화 이력 저장소 스텁. 프로세스가 죽으면 대화도 사라진다.

    요청마다 새로 만들면 이력이 남지 않으므로 하나를 공유해서 써야 한다.
    """

    def __init__(self) -> None:
        self._turns: dict[str, list[CounselTurn]] = defaultdict(list)
        self._owners: dict[str, str] = {}
        self._crisis: set[str] = set()
        self._lock = asyncio.Lock()

    async def load_turns(
        self,
        *,
        counsel_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[CounselTurn]:
        async with self._lock:
            if self._owners.get(counsel_id) not in (None, user_id):
                return []
            return list(self._turns[counsel_id][-limit:])

    async def append_turn(
        self,
        *,
        counsel_id: str,
        user_id: str,
        turn: CounselTurn,
    ) -> None:
        async with self._lock:
            self._owners.setdefault(counsel_id, user_id)
            if self._owners[counsel_id] != user_id:
                raise PermissionError("다른 사용자의 상담 세션에는 쓸 수 없습니다")
            self._turns[counsel_id].append(turn)

    async def mark_crisis(self, *, counsel_id: str, user_id: str) -> None:
        async with self._lock:
            self._owners.setdefault(counsel_id, user_id)
            if self._owners[counsel_id] != user_id:
                raise PermissionError("다른 사용자의 상담 세션에는 쓸 수 없습니다")
            self._crisis.add(counsel_id)

    async def is_crisis(self, *, counsel_id: str, user_id: str) -> bool:
        async with self._lock:
            if self._owners.get(counsel_id) not in (None, user_id):
                return False
            return counsel_id in self._crisis
