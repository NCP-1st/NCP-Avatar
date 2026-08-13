"""상담이 과거 일기를 **선택적으로** 참고하는지 검증한다 (H-02).

핵심은 "가져오느냐"가 아니라 **"언제 안 가져오느냐"**다. 매 턴 일기를 들이대면
상담이 아니라 기록 낭독이 된다. 그래서 세 층을 각각 본다.

  1. 검색 게이트  — 기억 제어·위기 세션·opening 단계
  2. 점수 임계값  — 약한 관련도는 아예 넣지 않는다
  3. 활용과 기록  — 프롬프트 주입, 가드레일 전환, counsel_evidences

2번의 임계값과 3번의 가드레일 전환이 이 기능의 중심이다. 임계값이 느슨하면
상관없는 일기가 새어 들어가고, 가드레일이 그대로면 근거가 확실한 문장까지
막혀서 일기를 붙인 의미가 사라진다.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.agents.counsel_chatbot.schemas import (
    ConversationState,
    CounselDraft,
    CounselRequest,
    CounselStage,
    CounselTurn,
    EmotionReading,
    ExtractedEvent,
    MemoryScope,
)
from backend.orchestration.counsel_flow import CounselFlow
from backend.repositories import SQLAlchemyConversationStore
from backend.services.knowledge import (
    DiaryLookup,
    DiaryReference,
    DiaryThresholds,
    InMemoryDiaryMemory,
    InMemoryPersonalOntology,
    SqlDiaryMemory,
)
from backend.services.knowledge.relevance import Candidate
from backend.services.knowledge.relevance import select as select_references
from database.models import (
    Base,
    CounselEvidence,
    CounselTurnTrace,
    DiarySession,
    DiaryVersion,
    User,
)

TODAY = date.today()


@pytest.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_diaries(db: AsyncSession) -> None:
    """u-1 에게 승인본·초안·오래된 일기·남의 일기를 하나씩 준다."""
    db.add_all([User(user_id="u-1"), User(user_id="u-2")])
    db.add_all(
        [
            DiarySession(
                session_id="s-recent", user_id="u-1", diary_date=TODAY - timedelta(days=3)
            ),
            DiarySession(
                session_id="s-draft", user_id="u-1", diary_date=TODAY - timedelta(days=4)
            ),
            DiarySession(
                session_id="s-old", user_id="u-1", diary_date=TODAY - timedelta(days=200)
            ),
            DiarySession(
                session_id="s-other", user_id="u-2", diary_date=TODAY - timedelta(days=3)
            ),
        ]
    )
    await db.flush()
    db.add_all(
        [
            # 같은 세션에 승인본 둘. created_at 을 명시해 어느 쪽이 대표인지
            # 못 박는다 — server_default 에 맡기면 둘이 같은 초에 찍혀 대표가
            # 흔들린다.
            DiaryVersion(
                version_id="v-old-approved", session_id="s-recent", title="옛 승인본",
                summary="예전에 승인한 요약", content="본문", approved=True,
                created_at=datetime(2026, 1, 1, 9, 0, 0),
            ),
            DiaryVersion(
                version_id="v-approved", session_id="s-recent", title="발표 준비",
                summary="발표 준비하느라 회사에서 늦게까지 남았다",
                # 본문에만 있고 제목·요약에는 없는 낱말을 심는다. 본문에만
                # 걸린 질의를 걸러내는지 보려면 이 구분이 있어야 한다.
                content="슬라이드를 고치고 또 고쳤다. 저녁은 김밥으로 때웠다.",
                approved=True, emotion_tags=["긴장"],
                created_at=datetime(2026, 1, 1, 10, 0, 0),
            ),
            # 초안만 있는 세션 — 사용자가 고르지 않은 글은 근거가 아니다.
            DiaryVersion(
                version_id="v-draft", session_id="s-draft", title="발표 초안",
                summary="발표 준비로 회사에서 야근했다", content="본문", approved=False,
            ),
            DiaryVersion(
                version_id="v-old", session_id="s-old", title="옛 발표",
                summary="발표 준비로 회사에 늦게까지 있었다", content="본문", approved=True,
            ),
            DiaryVersion(
                version_id="v-other", session_id="s-other", title="남의 발표",
                summary="발표 준비로 회사에서 야근했다", content="본문", approved=True,
            ),
        ]
    )
    await db.commit()


def _memory(db: AsyncSession, **overrides) -> SqlDiaryMemory:
    return SqlDiaryMemory(db, thresholds=DiaryThresholds(**overrides))


async def _references(memory, **kwargs) -> list[DiaryReference]:
    """프롬프트에 들어갈 목록만 꺼낸다.

    `search`는 걸러지기 전 후보 최고점도 같이 돌려준다. 그쪽은 관측 전용이라
    관련도 테스트에서는 보지 않는다 — 전용 테스트가 따로 있다.
    """
    return (await memory.search(**kwargs)).references


# --- 1. 검색 구현 -----------------------------------------------------------


@pytest.mark.anyio
async def test_search_returns_the_latest_approved_version_only(db: AsyncSession) -> None:
    """세션당 승인본 최신 1건. 초안 세션은 아예 나오지 않는다."""
    await _seed_diaries(db)

    found = await _references(
        _memory(db),         user_id="u-1", query="발표 준비 회사", period_days=30, max_items=5
    )

    assert [ref.session_id for ref in found] == ["s-recent"]
    assert found[0].summary.startswith("발표 준비하느라")  # 옛 승인본이 아니다
    assert found[0].emotion_tags == ["긴장"]


@pytest.mark.anyio
async def test_representative_version_is_stable_when_timestamps_tie(
    db: AsyncSession,
) -> None:
    """created_at 이 같아도 대표는 매번 같아야 한다.

    흔들리면 같은 질문에 턴마다 다른 일기를 근거로 대게 된다.
    """
    db.add(User(user_id="u-1"))
    db.add(DiarySession(session_id="s-tie", user_id="u-1", diary_date=TODAY))
    await db.flush()
    stamped = datetime(2026, 1, 1, 9, 0, 0)
    db.add_all(
        [
            DiaryVersion(
                version_id="v-a", session_id="s-tie", title="A",
                summary="발표 준비로 회사에서 야근했다 A", content="본문",
                approved=True, created_at=stamped,
            ),
            DiaryVersion(
                version_id="v-b", session_id="s-tie", title="B",
                summary="발표 준비로 회사에서 야근했다 B", content="본문",
                approved=True, created_at=stamped,
            ),
        ]
    )
    await db.commit()

    picks = set()
    for _ in range(5):
        found = await _references(
        _memory(db),             user_id="u-1", query="발표 준비 회사", period_days=30, max_items=5
        )
        assert len(found) == 1, "세션당 1건"
        picks.add(found[0].summary)

    assert len(picks) == 1, f"대표가 흔들린다: {picks}"


@pytest.mark.anyio
async def test_search_honours_the_period_window(db: AsyncSession) -> None:
    await _seed_diaries(db)

    found = await _references(
        _memory(db),         user_id="u-1", query="발표 준비 회사", period_days=365, max_items=5
    )

    assert {ref.session_id for ref in found} == {"s-recent", "s-old"}


@pytest.mark.anyio
async def test_search_never_returns_another_users_diary(db: AsyncSession) -> None:
    await _seed_diaries(db)

    found = await _references(
        _memory(db),         user_id="u-1", query="발표 준비 회사", period_days=365, max_items=5
    )

    assert "s-other" not in {ref.session_id for ref in found}


@pytest.mark.anyio
async def test_empty_query_returns_nothing(db: AsyncSession) -> None:
    """검색어가 없다고 아무 일기나 끌어오면 이 기능의 취지가 뒤집힌다."""
    await _seed_diaries(db)

    assert await _references(
        _memory(db),         user_id="u-1", query="", period_days=30, max_items=5
    ) == []


# --- 2. 임계값 --------------------------------------------------------------


@pytest.mark.anyio
async def test_single_token_query_hits_when_it_matches_the_headline(
    db: AsyncSession,
) -> None:
    """토픽이 하나여도 요약·제목에 걸리면 참조한다.

    실측에서 ContextAgent 는 topics 를 대개 **한 개**만 뽑는다(['국밥'],
    ['식사']). 2개를 요구하면 이 기능이 사실상 안 걸린다.
    """
    await _seed_diaries(db)

    found = await _references(
        _memory(db), user_id="u-1", query="발표", period_days=30, max_items=5
    )

    assert [ref.session_id for ref in found] == ["s-recent"]


@pytest.mark.anyio
async def test_content_only_match_is_rejected(db: AsyncSession) -> None:
    """본문에만 걸린 건 근거로 삼지 않는다.

    본문을 검색 대상에 넣으면 관련 일기를 훨씬 잘 찾지만, 실측에서 이런 게
    같이 걸렸다: "밥 먹는 것도 귀찮아요" → topics=['식사'] → 국밥 일기 본문의
    "식사를 마친 후에는…" 에 1.00. 밥맛 없다는 사람에게 국밥 일기를 꺼내는 꼴이다.
    """
    await _seed_diaries(db)

    # '김밥'·'저녁'은 본문에만 있다. 비율로는 1.0 이 나온다.
    found = await _references(
        _memory(db), user_id="u-1", query="김밥 저녁", period_days=30, max_items=5
    )

    assert found == [], "본문에만 걸린 일기를 근거로 대면 안 된다"


@pytest.mark.anyio
async def test_content_widens_the_match_when_the_headline_also_hits(
    db: AsyncSession,
) -> None:
    """머리말에 걸린 뒤라면 본문이 점수를 보탠다.

    요약 한 문장만 보면 맞출 표면이 너무 좁아, 같은 이야기를 해도 턴마다
    걸렸다 말았다 한다.
    """
    await _seed_diaries(db)

    # '발표'는 요약에, '슬라이드'는 본문에만 있다 → 2/2 = 1.0
    found = await _references(
        _memory(db), user_id="u-1", query="발표 슬라이드", period_days=30, max_items=5
    )

    assert [ref.session_id for ref in found] == ["s-recent"]
    assert found[0].score == 1.0
    assert "슬라이드" not in found[0].summary, "본문은 검색만 하고 넘기지 않는다"


@pytest.mark.anyio
async def test_weak_relevance_yields_nothing_at_all(db: AsyncSession) -> None:
    """최상위가 약하면 하나만 남기지 않고 전부 버린다.

    하나라도 넣으면 "어쨌든 뭐라도" 가 되어 상관없는 일기를 꺼내게 된다.
    """
    await _seed_diaries(db)

    # 5토큰 중 2개만 겹친다 → 0.4. min_score(0.5)에도 못 미친다.
    found = await _references(
        _memory(db),         user_id="u-1", query="발표 회사 김치찌개 노래방 자전거", period_days=30, max_items=5
    )
    assert found == []

    # 바닥은 넘지만(0.6) strong_score(0.7)에 못 미치는 구간도 비어야 한다.
    borderline = await _references(
        _memory(db),         user_id="u-1", query="발표 준비 회사 김치찌개 노래방", period_days=30, max_items=5
    )
    assert [round(ref.score, 2) for ref in borderline] == [], "0.6 은 약한 관련이다"


@pytest.mark.anyio
async def test_strong_relevance_passes(db: AsyncSession) -> None:
    await _seed_diaries(db)

    found = await _references(
        _memory(db),         user_id="u-1", query="발표 준비 회사", period_days=30, max_items=5
    )

    assert found and found[0].score >= 0.7


@pytest.mark.anyio
async def test_unmatched_emotion_does_not_dilute_the_score(db: AsyncSession) -> None:
    """감정 라벨이 안 맞아도 점수를 깎지 않는다.

    분모에 넣었더니 실측에서 topics=['발표','회사'] 가 둘 다 맞고도 감정 하나
    때문에 2/3=0.67 로 떨어져 탈락했다. 상담 쪽 감정 어휘(무덤덤·피로)와
    일기의 emotion_tags(긴장·평온)는 거의 겹치지 않는다.
    """
    await _seed_diaries(db)

    without = await _references(
        _memory(db),         user_id="u-1", query="발표 준비 회사", period_days=30, max_items=5
    )
    with_miss = await _references(
        _memory(db),         user_id="u-1", query="발표 준비 회사", period_days=30, max_items=5,
        emotion="무덤덤",  # 일기에 없는 감정
    )

    assert with_miss and without
    assert with_miss[0].score == without[0].score, "안 맞은 감정이 점수를 깎았다"


@pytest.mark.anyio
async def test_matched_emotion_raises_the_score(db: AsyncSession) -> None:
    """맞은 감정은 가산점으로 올린다."""
    await _seed_diaries(db)

    # 토픽 3개 중 2개가 맞아 0.67. 여기에 일기의 감정(긴장)이 맞으면 1.0 이 된다.
    plain = await _references(
        _memory(db, strong_score=0.6),         user_id="u-1", query="발표 준비 김치찌개", period_days=30, max_items=5
    )
    boosted = await _references(
        _memory(db, strong_score=0.6),         user_id="u-1", query="발표 준비 김치찌개", period_days=30, max_items=5,
        emotion="긴장",
    )

    assert plain and boosted
    assert round(plain[0].score, 2) == 0.67
    assert boosted[0].score == 1.0


def test_thresholds_come_from_config() -> None:
    """하드코딩이 아니라 config에서 온다."""
    thresholds = DiaryThresholds.from_config(
        {
            "counsel": {
                "diary_min_score": 0.31,
                "diary_min_match_tokens": 4,
                "diary_strong_score": 0.42,
            }
        }
    )

    assert (thresholds.min_score, thresholds.min_match_tokens, thresholds.strong_score) == (
        0.31,
        4,
        0.42,
    )


def test_select_cuts_to_max_items_by_score() -> None:
    references = [
        Candidate(
            reference=DiaryReference(
                session_id=f"s-{i}", diary_date=TODAY, summary="x", score=score
            ),
            matched=3,
            headline_matched=3,
        )
        for i, score in enumerate((0.8, 1.0, 0.9))
    ]

    kept = select_references(references, DiaryThresholds(), max_items=2)

    assert [ref.score for ref in kept] == [1.0, 0.9]


# --- 3. 흐름 게이트와 활용 ---------------------------------------------------


class _StubContextAgent:
    def __init__(self, *, topics: list[str] | None = None) -> None:
        self._topics = topics if topics is not None else ["발표", "준비", "회사"]

    async def structure(self, message: str, history: list[CounselTurn]) -> ConversationState:
        return ConversationState(
            events=[
                ExtractedEvent(summary="발표 준비", people=[], place=None, when_hint="지난주")
            ],
            emotion=EmotionReading(
                primary="긴장", secondary=[], intensity=3, confidence=0.8, evidence="떨려요"
            ),
            topics=list(self._topics),
            situation_clear=False,
            unclear_point="무엇이 가장 부담이었는지",
            wants_closure=False,
        )


class _StubCounselorAgent:
    """직전 답변과 겹치지 않게 매 턴 다르게 답한다 (style 검사 회피)."""

    model = "stub-model"
    _REPLIES = (
        ("그러셨군요.", "그때 어떤 점이 가장 부담이었어요?"),
        ("이야기해 주셔서 고마워요.", "요즘은 좀 어떠세요?"),
    )

    def __init__(self, reply: str | None = None) -> None:
        self.calls = 0
        self.seen_diary_refs: list = []
        self.seen_calls: list[list] = []
        self._forced = reply

    async def draft(self, **kwargs) -> CounselDraft:
        self.seen_diary_refs = list(kwargs.get("diary_refs") or [])
        self.seen_calls.append(self.seen_diary_refs)
        if self._forced is not None:
            self.calls += 1
            return CounselDraft(reply=self._forced, question=None, summary=None,
                                suggestion=None, suggestion_kind=None)
        reply, question = self._REPLIES[self.calls % len(self._REPLIES)]
        self.calls += 1
        return CounselDraft(reply=reply, question=question, summary=None,
                            suggestion=None, suggestion_kind=None)


class _ExplodingDiaryMemory:
    async def search(self, **kwargs) -> DiaryLookup:
        raise RuntimeError("일기 검색 장애")


def _flow(
    db: AsyncSession,
    counselor: _StubCounselorAgent | None = None,
    *,
    diary=None,
    context: _StubContextAgent | None = None,
) -> CounselFlow:
    return CounselFlow(
        context_agent=context or _StubContextAgent(),  # type: ignore[arg-type]
        counselor_agent=counselor or _StubCounselorAgent(),  # type: ignore[arg-type]
        ontology=InMemoryPersonalOntology(),
        store=SQLAlchemyConversationStore(db),
        diary=diary if diary is not None else SqlDiaryMemory(db),
    )


async def _run(flow: CounselFlow, message: str, **kwargs):
    return await flow.run(CounselRequest(user_id="u-1", message=message, **kwargs))


@pytest.mark.anyio
async def test_memory_scope_disabled_blocks_the_search(db: AsyncSession) -> None:
    """C-03. 일기 참조를 끈 사용자에게 일기를 들이밀지 않는다."""
    await _seed_diaries(db)
    counselor = _StubCounselorAgent()

    reply = await _run(
        _flow(db, counselor),
        "발표 준비 때문에 회사에서 계속 야근했어요",
        memory_scope=MemoryScope(enabled=False),
    )

    assert counselor.seen_diary_refs == []
    assert reply.trace.diary_count == 0


@pytest.mark.anyio
async def test_opening_stage_does_not_pull_the_past(db: AsyncSession) -> None:
    """첫 마디부터 과거를 꺼내면 듣기 전에 아는 척하는 게 된다."""
    await _seed_diaries(db)
    counselor = _StubCounselorAgent()

    reply = await _run(_flow(db, counselor), "발표 준비 때문에 회사에서 야근했어요")

    assert reply.stage is CounselStage.OPENING
    assert counselor.seen_diary_refs == []
    assert reply.trace.diary_count == 0


@pytest.mark.anyio
async def test_crisis_session_blocks_the_search(db: AsyncSession) -> None:
    await _seed_diaries(db)
    store = SQLAlchemyConversationStore(db)
    counselor = _StubCounselorAgent()
    flow = _flow(db, counselor)

    crisis = await _run(flow, "오늘 다 끝낼 생각이에요")
    assert await store.is_crisis(counsel_id=crisis.counsel_id, user_id="u-1")

    follow_up = await _run(
        flow, "발표 준비 때문에 회사에서 야근했어요", counsel_id=crisis.counsel_id
    )

    assert counselor.seen_diary_refs == [], "위기 세션에서는 일기를 찾지 않는다"
    assert follow_up.trace.diary_count == 0


@pytest.mark.anyio
async def test_diary_is_injected_once_past_opening(db: AsyncSession) -> None:
    await _seed_diaries(db)
    counselor = _StubCounselorAgent()
    flow = _flow(db, counselor)

    first = await _run(flow, "발표 준비 때문에 회사에서 야근했어요")
    assert counselor.seen_diary_refs == [], "opening 단계"

    reply = await _run(flow, "계속 그 생각이 나요", counsel_id=first.counsel_id)

    assert reply.stage is CounselStage.EXPLORING
    assert [ref.session_id for ref in counselor.seen_diary_refs] == ["s-recent"]
    assert reply.trace.diary_count == 1
    assert reply.trace.diary_top_score is not None and reply.trace.diary_top_score >= 0.7


@pytest.mark.anyio
async def test_weakly_related_turn_injects_nothing(db: AsyncSession) -> None:
    """관련이 약하면 블록 없이 평범하게 답한다."""
    await _seed_diaries(db)
    counselor = _StubCounselorAgent()
    flow = _flow(db, counselor, context=_StubContextAgent(topics=["점심", "메뉴", "커피"]))

    first = await _run(flow, "점심 메뉴 고르기가 힘들어요")
    reply = await _run(flow, "커피도 마셨어요", counsel_id=first.counsel_id)

    assert counselor.seen_diary_refs == []
    assert reply.trace.diary_count == 0
    assert reply.trace.diary_top_score is None


@pytest.mark.anyio
async def test_diary_search_failure_does_not_break_the_reply(db: AsyncSession) -> None:
    """검색 장애가 상담 실패가 되면 안 된다."""
    await _seed_diaries(db)
    flow = _flow(db, diary=_ExplodingDiaryMemory())

    first = await _run(flow, "발표 준비 때문에 회사에서 야근했어요")
    reply = await _run(flow, "계속 그 생각이 나요", counsel_id=first.counsel_id)

    assert reply.message, "답변은 정상적으로 나와야 한다"
    assert reply.trace.result_code in {"ok", "guardrail_rewrite"}
    assert reply.trace.diary_count == 0


# --- 4. 가드레일 전환과 근거 기록 --------------------------------------------


@pytest.mark.anyio
async def test_past_claim_guardrail_relaxes_when_a_diary_is_injected(
    db: AsyncSession,
) -> None:
    """일기가 들어갔으면 과거 단정을 막지 않는다. 이 전환이 기능의 중심이다."""
    await _seed_diaries(db)
    counselor = _StubCounselorAgent()
    flow = _flow(db, counselor)
    first = await _run(flow, "발표 준비 때문에 회사에서 야근했어요")

    # `review_past_claims` 가 잡는 표현을 일부러 낸다.
    counselor._forced = "저번에도 비슷한 일로 힘들어하셨죠."
    reply = await _run(flow, "계속 그 생각이 나요", counsel_id=first.counsel_id)

    assert reply.trace.diary_count == 1, "일기가 주입된 상황이어야 한다"
    assert "past_speculation" not in reply.trace.guardrail_hits
    assert reply.message.startswith("저번에도"), "답변이 폴백으로 바뀌지 않아야 한다"


@pytest.mark.anyio
async def test_past_claim_guardrail_still_fires_without_a_diary(
    db: AsyncSession,
) -> None:
    """일기가 안 들어간 턴은 예전과 똑같이 막는다 (기존 동작 유지)."""
    db.add(User(user_id="u-1"))
    await db.commit()
    counselor = _StubCounselorAgent()
    flow = _flow(db, counselor)
    first = await _run(flow, "발표 준비 때문에 회사에서 야근했어요")

    counselor._forced = "저번에도 비슷한 일로 힘들어하셨죠."
    reply = await _run(flow, "계속 그 생각이 나요", counsel_id=first.counsel_id)

    assert reply.trace.diary_count == 0
    assert "past_speculation" in reply.trace.guardrail_hits
    assert not reply.message.startswith("저번에도"), "안전 폴백으로 대체돼야 한다"


@pytest.mark.anyio
async def test_a_date_the_user_never_mentioned_is_blocked(db: AsyncSession) -> None:
    """일기도 없고 사용자가 꺼낸 적도 없는 시점을 단정하면 막는다."""
    db.add(User(user_id="u-1"))
    await db.commit()
    counselor = _StubCounselorAgent()
    flow = _flow(db, counselor)
    first = await _run(flow, "요즘 좀 지쳐요")

    counselor._forced = "지난주에 친구분들과 시간을 보내셨죠."
    reply = await _run(flow, "이야기하고 싶어요", counsel_id=first.counsel_id)

    assert "past_fabrication" in reply.trace.guardrail_hits
    assert not reply.message.startswith("지난주에"), "안전 폴백으로 대체돼야 한다"


@pytest.mark.anyio
async def test_the_same_sentence_passes_when_the_user_brought_it_up(
    db: AsyncSession,
) -> None:
    """사용자가 꺼낸 시점을 되받는 건 반영이다. 막으면 상담이 성립하지 않는다.

    `_user_said` 가 대화를 넘기지 않으면 이 테스트가 깨진다.
    """
    db.add(User(user_id="u-1"))
    await db.commit()
    counselor = _StubCounselorAgent()
    flow = _flow(db, counselor)
    first = await _run(flow, "지난주에 친구들이랑 놀러 갔어요")

    counselor._forced = "지난주에 친구분들과 시간을 보내셨죠."
    reply = await _run(flow, "그때 얘기 하고 싶어요", counsel_id=first.counsel_id)

    assert "past_fabrication" not in reply.trace.guardrail_hits
    assert reply.message.startswith("지난주에")


@pytest.mark.anyio
async def test_the_counsellors_own_earlier_words_do_not_count_as_grounding(
    db: AsyncSession,
) -> None:
    """한 번 지어낸 과거가 다음 턴부터 사실로 굳으면 안 된다."""
    db.add(User(user_id="u-1"))
    await db.commit()
    counselor = _StubCounselorAgent()
    flow = _flow(db, counselor)
    first = await _run(flow, "요즘 좀 지쳐요")

    counselor._forced = "지난주에 친구분들과 시간을 보내셨죠."
    await _run(flow, "이야기하고 싶어요", counsel_id=first.counsel_id)
    # 사용자는 여전히 '지난주'를 꺼낸 적이 없다.
    again = await _run(flow, "네 그렇군요", counsel_id=first.counsel_id)

    assert "past_fabrication" in again.trace.guardrail_hits


@pytest.mark.anyio
async def test_only_injected_diaries_are_recorded_as_evidence(db: AsyncSession) -> None:
    await _seed_diaries(db)
    flow = _flow(db)

    first = await _run(flow, "발표 준비 때문에 회사에서 야근했어요")
    await _run(flow, "계속 그 생각이 나요", counsel_id=first.counsel_id)

    rows = (await db.execute(select(CounselEvidence))).scalars().all()

    assert len(rows) == 1, "opening 턴에는 근거가 없어야 한다"
    assert rows[0].diary_session_id == "s-recent"
    assert rows[0].diary_date == TODAY - timedelta(days=3)  # 카드 스냅샷
    assert rows[0].relevance_score is not None


@pytest.mark.anyio
async def test_reply_carries_the_evidence_for_the_screen(db: AsyncSession) -> None:
    """화면이 "몇 월 며칠 일기를 참고했다"를 그릴 수 있어야 한다 (H-02)."""
    await _seed_diaries(db)
    flow = _flow(db)

    first = await _run(flow, "발표 준비 때문에 회사에서 야근했어요")
    assert first.evidences == [], "참고한 게 없으면 비어 있어야 한다"

    reply = await _run(flow, "계속 그 생각이 나요", counsel_id=first.counsel_id)

    assert [ref.diary_date for ref in reply.evidences] == [TODAY - timedelta(days=3)]
    assert reply.evidences[0].session_id == "s-recent"


@pytest.mark.anyio
async def test_fallback_replies_claim_no_evidence(db: AsyncSession) -> None:
    """버려진 답변의 근거를 남기면 감사 기록이 거짓이 된다."""
    await _seed_diaries(db)
    flow = _flow(db)

    crisis = await _run(flow, "오늘 다 끝낼 생각이에요")

    assert crisis.evidences == []
    assert (await db.execute(select(CounselEvidence))).scalars().all() == []


@pytest.mark.anyio
async def test_in_memory_stub_applies_the_same_thresholds() -> None:
    """스텁이 느슨하면 스텁으로 통과한 테스트가 실제 DB에서 다르게 동작한다."""
    entries = [
        DiaryReference(
            session_id="s-1", diary_date=TODAY, summary="발표 준비로 회사에서 야근했다"
        )
    ]
    memory = InMemoryDiaryMemory(entries)

    strong = await _references(
        memory, user_id="u-1", query="발표 준비 회사", period_days=30, max_items=5
    )
    # 3토큰 중 1개만 겹친다 → 0.33. min_score(0.5) 아래다.
    weak = await _references(
        memory, user_id="u-1", query="발표 김치찌개 노래방", period_days=30, max_items=5
    )

    assert [ref.session_id for ref in strong] == ["s-1"]
    assert weak == [], "관련이 약하면 스텁도 버린다"


@pytest.mark.anyio
async def test_in_memory_stub_honours_the_period_window() -> None:
    entries = [
        DiaryReference(
            session_id="s-old",
            diary_date=TODAY - timedelta(days=90),
            summary="발표 준비로 회사에서 야근했다",
        )
    ]
    memory = InMemoryDiaryMemory(entries)

    assert await _references(
        memory, user_id="u-1", query="발표 준비 회사", period_days=30, max_items=5
    ) == []
    assert await _references(
        memory, user_id="u-1", query="발표 준비 회사", period_days=365, max_items=5
    ) != []


# --- 5. 임계값 보정용 관측 ---------------------------------------------------
#
# 참조에 성공한 턴은 counsel_evidences 로도 알 수 있다. 여기서 지키는 건
# **떨어진 턴**의 기록이다 — 임계값을 옮길지 정하는 근거가 그쪽이다.


@pytest.mark.anyio
async def test_rejected_candidates_still_report_their_best_score(
    db: AsyncSession,
) -> None:
    """임계값에 걸려 아무것도 안 나와도 후보 최고점은 남는다.

    이게 없으면 "아깝게 떨어진 0.67"과 "아예 무관한 0.0"이 관측에서 똑같이
    보인다. 그 둘을 구별 못 하면 기준을 낮출지 판단할 수 없다.
    """
    await _seed_diaries(db)

    # 5토큰 중 2개만 겹쳐 0.4 — min_score(0.5) 미달로 전부 탈락한다.
    lookup = await _memory(db).search(
        user_id="u-1", query="발표 회사 김치찌개 노래방 자전거", period_days=30, max_items=5
    )

    assert lookup.references == []
    assert lookup.top_candidate_score == pytest.approx(0.4)


@pytest.mark.anyio
async def test_no_candidates_at_all_reports_no_score(db: AsyncSession) -> None:
    """기간 안에 승인된 일기가 없으면 점수 자체가 없다. 0.0 이 아니라 None."""
    db.add(User(user_id="u-1"))
    await db.commit()

    lookup = await _memory(db).search(
        user_id="u-1", query="발표 준비 회사", period_days=30, max_items=5
    )

    assert lookup.references == []
    assert lookup.top_candidate_score is None


@pytest.mark.anyio
async def test_accepted_lookup_reports_both_scores(db: AsyncSession) -> None:
    await _seed_diaries(db)

    lookup = await _memory(db).search(
        user_id="u-1", query="발표 준비 회사", period_days=30, max_items=5
    )

    assert lookup.references
    assert lookup.top_candidate_score == lookup.references[0].score


@pytest.mark.anyio
async def test_in_memory_stub_reports_the_same_observation() -> None:
    """스텁이 다른 값을 남기면 그 숫자로 임계값을 옮기게 된다."""
    memory = InMemoryDiaryMemory(
        [
            DiaryReference(
                session_id="s-1", diary_date=TODAY, summary="발표 준비로 회사에서 야근했다"
            )
        ]
    )

    lookup = await memory.search(
        user_id="u-1", query="발표 회사 김치찌개 노래방 자전거", period_days=30, max_items=5
    )

    assert lookup.references == []
    assert lookup.top_candidate_score == pytest.approx(0.4)


@pytest.mark.anyio
async def test_trace_carries_the_candidate_score_when_nothing_is_injected(
    db: AsyncSession,
) -> None:
    """흐름을 거쳐도 후보 최고점이 트레이스까지 온다.

    5토큰 중 발표·회사가 맞아 2, 흐름이 넘긴 감정(긴장)이 일기 태그와 맞아
    가산점 1 → 0.6. min_score(0.5)는 넘지만 strong_score(0.7)에 못 미쳐
    참조는 0건이다. **딱 이 구간**이 임계값 조정에서 보고 싶은 표본이다.
    """
    await _seed_diaries(db)
    # 검색 질의는 topics 로 만들어진다. 일부러 약하게 겹치도록 준다.
    context = _StubContextAgent(topics=["발표", "김치찌개", "노래방", "자전거", "회사"])
    flow = _flow(db, context=context)

    first = await _run(flow, "요즘 어떻게 지내는지 이야기하고 싶어요")
    reply = await _run(flow, "계속 그 생각이 나요", counsel_id=first.counsel_id)

    assert reply.trace.diary_count == 0
    assert reply.trace.diary_top_score is None, "쓰지 않은 일기를 쓴 것처럼 남기면 안 된다"
    assert reply.trace.diary_top_candidate == pytest.approx(0.6)


@pytest.mark.anyio
async def test_gated_turns_report_no_candidate_score(db: AsyncSession) -> None:
    """검색을 아예 하지 않은 턴은 점수도 없다 (C-03).

    막힌 턴에 숫자가 실리면 임계값 분포에 검색하지도 않은 표본이 섞인다.
    """
    await _seed_diaries(db)
    flow = _flow(db)

    first = await _run(flow, "발표 준비 때문에 회사에서 야근했어요")
    reply = await _run(
        flow,
        "계속 그 생각이 나요",
        counsel_id=first.counsel_id,
        memory_scope=MemoryScope(enabled=False),
    )

    assert reply.trace.diary_count == 0
    assert reply.trace.diary_top_candidate is None


@pytest.mark.anyio
async def test_observation_reaches_the_database(db: AsyncSession) -> None:
    """트레이스에만 있고 DB에 안 들어가면 분포를 볼 수가 없다.

    이 기능이 붙기 전에는 스키마에는 있고 컬럼이 없어 조용히 버려졌다.
    """
    await _seed_diaries(db)
    context = _StubContextAgent(topics=["발표", "김치찌개", "노래방", "자전거", "회사"])
    flow = _flow(db, context=context)

    first = await _run(flow, "요즘 어떻게 지내는지 이야기하고 싶어요")
    await _run(flow, "계속 그 생각이 나요", counsel_id=first.counsel_id)

    await db.rollback()  # 흐름이 커밋한 것만 읽는다
    rows = (
        (await db.execute(select(CounselTurnTrace).order_by(CounselTurnTrace.id)))
        .scalars()
        .all()
    )

    assert rows, "어시스턴트 턴마다 트레이스가 있어야 한다"
    assert rows[-1].diary_count == 0
    assert rows[-1].diary_top_score is None
    assert rows[-1].diary_top_candidate == pytest.approx(0.6)


@pytest.mark.anyio
async def test_database_records_the_accepted_score_too(db: AsyncSession) -> None:
    await _seed_diaries(db)
    flow = _flow(db)

    first = await _run(flow, "발표 준비 때문에 회사에서 야근했어요")
    await _run(flow, "계속 그 생각이 나요", counsel_id=first.counsel_id)

    await db.rollback()
    rows = (
        (await db.execute(select(CounselTurnTrace).order_by(CounselTurnTrace.id)))
        .scalars()
        .all()
    )

    assert rows[-1].diary_count == 1
    assert rows[-1].diary_top_score is not None
    assert rows[-1].diary_top_candidate == rows[-1].diary_top_score
