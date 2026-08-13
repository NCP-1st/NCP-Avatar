"""회상 단계가 흐름 안에서 안전 규칙을 넘어서지 않는지.

단위 테스트는 `_decide_stage`를 직접 부른다. 하지만 위기 세션에서는 흐름이
`_decide_stage`를 **아예 부르지 않고** EXPLORING으로 고정한다. 그 성질은
흐름을 돌려봐야 확인된다 — 회상이 위기를 가로채면 자해 신호를 말한 사람에게
일기를 읽어주게 된다.
"""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.agents.counsel_chatbot.schemas import (
    ConversationState,
    CounselDraft,
    CounselRequest,
    CounselStage,
    CounselTurn,
    EmotionReading,
    MemoryScope,
    SafetyLevel,
)
from backend.orchestration.counsel_flow import CounselFlow
from backend.repositories import SQLAlchemyConversationStore
from backend.services.knowledge import (
    DiaryLookup,
    DiaryReference,
    InMemoryDiaryMemory,
    InMemoryPersonalOntology,
)
from database.models import Base


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


class _RecallContextAgent:
    """무슨 말을 하든 회상으로 구조화한다. 게이트만 보기 위한 것이다."""

    async def structure(self, message: str, history: list[CounselTurn]) -> ConversationState:
        return ConversationState(
            events=[],
            emotion=EmotionReading(
                primary="무덤덤", secondary=[], intensity=2, confidence=0.5, evidence=""
            ),
            topics=["국밥"],
            situation_clear=False,
            unclear_point="어떤 국밥이었는지",
            intent="recall",
            wants_closure=False,
        )


class _AskingCounselorAgent:
    """지시를 어기고 질문·제안을 꽉 채워 돌려준다."""

    model = "stub-model"

    def __init__(self) -> None:
        self.seen_stage: CounselStage | None = None
        self.seen_diary_refs: list = []

    async def draft(self, **kwargs) -> CounselDraft:
        self.seen_stage = kwargs.get("stage")
        self.seen_diary_refs = list(kwargs.get("diary_refs") or [])
        return CounselDraft(
            reply="지난번에 국밥을 드셨네요.",
            question="어떤 계기로 드시게 됐어요?",
            summary="국밥을 드신 날의 정리",
            suggestion="따뜻한 국물 한 그릇 어떠세요",
            suggestion_kind="action",
        )


class _EmptyDiaryMemory:
    """검색은 되는데 걸리는 게 없다."""

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, **kwargs) -> DiaryLookup:
        self.calls += 1
        return DiaryLookup()


class _OneDiaryMemory:
    """국밥 일기 한 건이 걸린다.

    근거가 있어야 과거를 말할 수 있다. 없으면 `review_past_claims`가 "지난번에"
    같은 표현을 막는데, 그건 이 파일에서 따로 검증한다.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, **kwargs) -> DiaryLookup:
        self.calls += 1
        return DiaryLookup(
            references=[
                DiaryReference(
                    session_id="s-1",
                    diary_date=date(2026, 8, 11),
                    title="국밥 먹은 날",
                    summary="국밥을 먹고 소소한 행복을 느꼈다",
                    emotion_tags=[],
                    score=0.68,
                )
            ],
            top_candidate_score=0.68,
        )


def _flow(db: AsyncSession, counselor, *, diary=None) -> CounselFlow:
    return CounselFlow(
        context_agent=_RecallContextAgent(),  # type: ignore[arg-type]
        counselor_agent=counselor,  # type: ignore[arg-type]
        ontology=InMemoryPersonalOntology(),
        store=SQLAlchemyConversationStore(db),
        diary=diary if diary is not None else InMemoryDiaryMemory(),
    )


# --- 위기가 언제나 우선 ---------------------------------------------------------


@pytest.mark.anyio
async def test_a_crisis_message_never_becomes_a_recall_turn(db: AsyncSession) -> None:
    """구조화가 recall 이라고 해도 위기가 이긴다.

    위기는 구조화보다 **먼저** 판정되고 흐름을 그 자리에서 끊는다.
    """
    counselor = _AskingCounselorAgent()
    reply = await _flow(db, counselor).run(
        CounselRequest(user_id="u-1", message="죽고 싶어요. 국밥 먹었던 거 기억나?")
    )

    assert reply.safety_level is SafetyLevel.CRISIS
    assert reply.trace.result_code == "crisis_redirect"
    assert reply.stage is not CounselStage.RECALL
    # 상담가 에이전트를 아예 부르지 않는다.
    assert counselor.seen_stage is None


@pytest.mark.anyio
async def test_a_crisis_session_stays_in_exploring_on_later_recall(
    db: AsyncSession,
) -> None:
    """위기가 한 번 있었던 세션은 이후 회상 질문에도 EXPLORING 으로 고정된다."""
    counselor = _AskingCounselorAgent()
    flow = _flow(db, counselor)
    first = await flow.run(
        CounselRequest(user_id="u-1", message="자해하고 싶어요")
    )
    assert first.safety_level is SafetyLevel.CRISIS

    await flow.run(
        CounselRequest(
            user_id="u-1",
            message="국밥 먹었던 거 기억나?",
            counsel_id=first.counsel_id,
        )
    )

    assert counselor.seen_stage is CounselStage.EXPLORING


# --- 회상 턴은 일기를 찾는다 -----------------------------------------------------


@pytest.mark.anyio
async def test_recall_still_searches_the_diary(db: AsyncSession) -> None:
    """회상인데 일기를 안 뽑으면 답할 근거가 없다."""
    diary = _EmptyDiaryMemory()
    counselor = _AskingCounselorAgent()

    await _flow(db, counselor, diary=diary).run(
        CounselRequest(user_id="u-1", message="국밥 먹었던 거 기억나?")
    )

    assert counselor.seen_stage is CounselStage.RECALL
    assert diary.calls == 1


@pytest.mark.anyio
async def test_memory_off_skips_the_search_even_for_recall(db: AsyncSession) -> None:
    """기억 제어(C-03)가 회상보다 위다. 껐으면 찾지 않는다."""
    diary = _EmptyDiaryMemory()

    await _flow(db, _AskingCounselorAgent(), diary=diary).run(
        CounselRequest(
            user_id="u-1",
            message="국밥 먹었던 거 기억나?",
            memory_scope=MemoryScope(enabled=False),
        )
    )

    assert diary.calls == 0


# --- 질문이 사용자에게 나가지 않는다 ----------------------------------------------


@pytest.mark.anyio
async def test_the_question_never_reaches_the_user(db: AsyncSession) -> None:
    """모델이 질문·제안·정리를 다 채워 와도 화면에는 reply 만 나간다."""
    reply = await _flow(db, _AskingCounselorAgent(), diary=_OneDiaryMemory()).run(
        CounselRequest(user_id="u-1", message="국밥 먹었던 거 기억나?")
    )

    assert reply.stage is CounselStage.RECALL
    assert reply.sections is not None
    assert reply.sections.question is None
    assert reply.sections.summary is None
    assert reply.sections.suggestion is None
    assert "어떤 계기로" not in reply.message
    assert reply.message.strip() == "지난번에 국밥을 드셨네요."


@pytest.mark.anyio
async def test_no_diary_means_the_past_claim_gate_still_runs(db: AsyncSession) -> None:
    """일기가 하나도 없으면 근거 없는 과거 단정 검사는 그대로 걸린다."""

    class _InventingCounselor(_AskingCounselorAgent):
        async def draft(self, **kwargs) -> CounselDraft:
            self.seen_stage = kwargs.get("stage")
            return CounselDraft(
                reply="예전에도 늘 그러셨잖아요. 매번 국밥을 드셨었죠.",
                question=None, summary=None, suggestion=None, suggestion_kind=None,
            )

    counselor = _InventingCounselor()
    reply = await _flow(db, counselor, diary=_EmptyDiaryMemory()).run(
        CounselRequest(user_id="u-1", message="국밥 먹었던 거 기억나?")
    )

    assert counselor.seen_stage is CounselStage.RECALL
    assert reply.trace.guardrail_hits, "근거 없는 과거 단정이 걸러지지 않았다"
