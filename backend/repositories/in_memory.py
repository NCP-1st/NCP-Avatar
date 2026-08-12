import asyncio
from collections import defaultdict
from datetime import datetime, timezone

from backend.agents.counsel_chatbot.schemas import (
    CounselHistory,
    CounselHistoryTurn,
    CounselSessionSummary,
    CounselTrace,
    CounselTurn,
    SafetyLevel,
)
from backend.api.schemas import DiarySession, NormalizedInputItem
from backend.repositories.base import title_from_message
from backend.services.knowledge.base import DiaryReference

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


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
        self._touched: dict[str, datetime] = {}
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
        trace: CounselTrace | None = None,
        safety_level: str | None = None,
        diary_refs: list[DiaryReference] | None = None,
    ) -> None:
        # 트레이스·근거는 받기만 하고 버린다. 스텁은 대화 이력만 들고 있으면 된다.
        async with self._lock:
            self._owners.setdefault(counsel_id, user_id)
            if self._owners[counsel_id] != user_id:
                raise PermissionError("다른 사용자의 상담 세션에는 쓸 수 없습니다")
            self._turns[counsel_id].append(turn)
            self._touched[counsel_id] = datetime.now(timezone.utc)

    async def list_sessions(
        self,
        *,
        user_id: str,
        limit: int = 20,
    ) -> list[CounselSessionSummary]:
        async with self._lock:
            summaries = [
                CounselSessionSummary(
                    counsel_id=counsel_id,
                    title=title_from_message(
                        next(
                            (t.content for t in turns if t.role == "user"),
                            None,
                        )
                    ),
                    last_active_at=self._touched.get(counsel_id, _EPOCH),
                    turn_count=len(turns),
                    safety_level=(
                        SafetyLevel.CRISIS
                        if counsel_id in self._crisis
                        else SafetyLevel.NORMAL
                    ),
                    is_crisis=counsel_id in self._crisis,
                )
                for counsel_id, turns in self._turns.items()
                if self._owners.get(counsel_id) == user_id and turns
            ]
        summaries.sort(key=lambda s: s.last_active_at, reverse=True)
        return summaries[:limit]

    async def load_history(
        self,
        *,
        counsel_id: str,
        user_id: str,
    ) -> CounselHistory:
        async with self._lock:
            if self._owners.get(counsel_id) != user_id:
                raise PermissionError("이 상담 세션에 접근할 수 없습니다")
            turns = list(self._turns[counsel_id])
        # 스텁은 근거를 버리므로 evidences 는 늘 비어 있다. 화면에서 근거
        # 표시가 사라지는 걸 확인하려면 SQL 저장소로 봐야 한다.
        return CounselHistory(
            counsel_id=counsel_id,
            turns=[
                CounselHistoryTurn(
                    role=turn.role, content=turn.content, stage=turn.stage
                )
                for turn in turns
            ],
        )

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
