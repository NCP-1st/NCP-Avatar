from typing import Protocol

from backend.agents.counsel_chatbot.schemas import (
    CounselHistory,
    CounselSessionSummary,
    CounselTrace,
    CounselTurn,
)
from backend.api.schemas import DiarySession, NormalizedInputItem
from backend.services.knowledge.base import DiaryReference


_TITLE_MAX = 30


def title_from_message(message: str | None) -> str:
    """첫 사용자 발화로 상담 목록에 쓸 제목을 만든다.

    저장소 구현들이 공유한다. 각자 만들면 스텁으로 통과한 테스트가 실제
    DB에서 다른 제목을 낸다.

    모델을 부르지 않는다. 목록을 그리자고 지난 상담 스무 개마다 요약을
    생성하면 화면 한 번 여는 데 스무 번의 LLM 호출이 붙는다.
    """
    text = " ".join((message or "").split())
    if not text:
        return "제목 없는 대화"
    if len(text) <= _TITLE_MAX:
        return text
    return text[: _TITLE_MAX - 1].rstrip() + "…"


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
        trace: CounselTrace | None = None,
        safety_level: str | None = None,
        diary_refs: list[DiaryReference] | None = None,
    ) -> None:
        """대화 한 줄을 덧붙인다. 세션이 없으면 만든다.

        `trace`·`safety_level`·`diary_refs`는 어시스턴트 턴에만 온다. 관측·안전
        감사와 근거 기록용이라 저장소가 버려도 상담은 그대로 동작한다 —
        필요한 저장소만 남기면 된다.

        `diary_refs`는 그 답변에 **실제로 주입된** 일기다. 검색만 되고 임계값에
        걸려 버려진 것은 근거가 아니다.
        """
        ...

    async def list_sessions(
        self,
        *,
        user_id: str,
        limit: int = 20,
    ) -> list[CounselSessionSummary]:
        """이 사용자의 지난 상담을 최근 활동 순으로 돌려준다.

        `user_id`의 것만 돌려줘야 한다 — `load_turns`와 같은 이유다.

        턴이 하나도 없는 세션은 내보내지 않는다. 사용자가 첫 마디를 보내는
        순간 세션 행이 먼저 생기는데, 그 요청이 실패하면 빈 세션이 남는다.
        목록에 제목 없는 빈 줄이 쌓이면 지난 상담을 찾기가 더 어려워진다.
        """
        ...

    async def load_history(
        self,
        *,
        counsel_id: str,
        user_id: str,
    ) -> CounselHistory:
        """지난 상담 하나를 화면에 다시 그릴 수 있게 통째로 돌려준다.

        `load_turns`와 달리 최근 N개로 자르지 않는다. 그쪽은 모델에 넣을
        맥락이라 짧아야 하지만, 이건 사용자가 읽던 대화라 중간이 잘리면
        안 된다.

        남의 것이면 `PermissionError`. 빈 목록으로 돌려주면 "없는 상담"과
        "남의 상담"이 구분되지 않아 호출부가 404와 403을 가릴 수 없다.
        """
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
