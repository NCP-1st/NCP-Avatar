"""임베딩 기반 일기 검색 (상담이 쓰는 읽기 경로).

관련도보다 먼저 지켜야 하는 것부터 본다 — 남의 일기가 새지 않는가, 기억
범위를 지키는가, 본문이 새어 나가지 않는가.

적재는 `services/embedding`이 하고 여기서는 읽기만 검증한다. 테이블은
마이그레이션(`d4e5f6a7b8c9`)이 만든 것을 그대로 쓴다 — 테스트가 스키마를
따로 만들면 운영과 갈라진다.

**아무것도 커밋하지 않는다.** 트랜잭션을 열고 끝에 되돌린다. 붙는 DB가 운영
DB일 수 있어서, 테스트가 남긴 행이 상담 근거로 조회되면 안 된다.

pgvector를 쓸 수 있는 PostgreSQL이 없으면 통째로 skip한다 — `Vector` 컬럼은
sqlite에서 만들 수 없다.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.services.embedding.clova_embedding import EMBEDDING_DIMENSIONS
from backend.services.knowledge.diary_vector import VectorDiaryMemory
from backend.services.knowledge.vector_thresholds import VectorThresholds
from database.models import DiaryEmbedding, DiarySession, DiaryVersion, User

TODAY = date.today()


def _dsn() -> str | None:
    """테스트가 붙을 PostgreSQL.

    `TEST_PG_DSN`을 주면 그쪽을 쓴다 — 운영 DB에 붙기 싫을 때를 위한 것이다.
    없으면 앱이 쓰는 DB에 붙되, 모든 쓰기는 되돌린다.
    """
    override = os.getenv("TEST_PG_DSN")
    if override:
        return override
    try:
        from database.conn.db import DATABASE_URL
    except Exception:  # pragma: no cover - 설정이 없는 환경
        return None
    return DATABASE_URL if DATABASE_URL.startswith("postgresql") else None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def db() -> AsyncSession:
    dsn = _dsn()
    if dsn is None:
        pytest.skip("pgvector를 쓸 수 있는 PostgreSQL이 없다")

    engine = create_async_engine(dsn)
    connection = await engine.connect()
    transaction = await connection.begin()
    try:
        if not await connection.scalar(
            text("SELECT COUNT(*) FROM pg_extension WHERE extname = 'vector'")
        ):
            pytest.skip("이 DB에 pgvector 확장이 없다")

        session = AsyncSession(bind=connection, expire_on_commit=False)
        yield session
        await session.close()
    finally:
        # 커밋하지 않는다. 운영 DB에 붙어도 흔적이 남지 않아야 한다.
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


class _StubEmbedder:
    """항상 같은 벡터를 돌려주는 어댑터.

    `EmbeddingAdapter` 프로토콜만 만족하면 되므로 네트워크를 타지 않는다.
    """

    def __init__(self, vector: list[float]) -> None:
        self.vector = vector
        self.calls: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return self.vector


def _vector(*values: float) -> list[float]:
    """저장 컬럼과 같은 차원으로 맞춘다. 나머지는 0으로 채운다."""
    return list(values) + [0.0] * (EMBEDDING_DIMENSIONS - len(values))


async def _seed(
    db: AsyncSession,
    *,
    user_id: str,
    session_id: str,
    version_id: str,
    embedding: list[float],
    diary_date: date | None = None,
    summary: str = "국밥을 먹고 행복했다",
    approved: bool = True,
) -> None:
    if await db.get(User, user_id) is None:
        db.add(User(user_id=user_id))
    if await db.get(DiarySession, session_id) is None:
        db.add(
            DiarySession(
                session_id=session_id,
                user_id=user_id,
                diary_date=diary_date or TODAY,
                status="completed",
            )
        )
    await db.flush()
    db.add(
        DiaryVersion(
            version_id=version_id,
            session_id=session_id,
            title="제목",
            summary=summary,
            content="본문 전체는 검색에만 쓰고 밖으로 내보내지 않는다",
            approved=approved,
        )
    )
    await db.flush()
    db.add(DiaryEmbedding(version_id=version_id, embedding=embedding))
    await db.flush()


def _memory(db: AsyncSession, *, query_vector: list[float]) -> VectorDiaryMemory:
    return VectorDiaryMemory(db, _StubEmbedder(query_vector))


# --- 1. 소유권 ---------------------------------------------------------------


@pytest.mark.anyio
async def test_another_users_diary_never_leaks(db: AsyncSession) -> None:
    """남의 일기가 근거로 나가면 그 자체가 사고다.

    `DiaryEmbeddingService.find_similar_diaries`는 사용자를 가리지 않는다.
    상담 경로가 그걸 쓰면 안 되는 이유가 이 테스트다.
    """
    await _seed(db, user_id="u-1", session_id="vs-mine", version_id="vv-mine",
                embedding=_vector(1, 0))
    await _seed(db, user_id="u-2", session_id="vs-theirs", version_id="vv-theirs",
                embedding=_vector(1, 0))

    found = await _memory(db, query_vector=_vector(1, 0)).search(
        user_id="u-1", query="국밥", period_days=30, max_items=5
    )

    assert [ref.session_id for ref in found.references] == ["vs-mine"]


# --- 2. 기억 범위 (C-03) ------------------------------------------------------


@pytest.mark.anyio
async def test_diaries_outside_the_period_are_excluded(db: AsyncSession) -> None:
    await _seed(db, user_id="u-1", session_id="vs-recent", version_id="vv-recent",
                embedding=_vector(1, 0), diary_date=TODAY - timedelta(days=3))
    await _seed(db, user_id="u-1", session_id="vs-old", version_id="vv-old",
                embedding=_vector(1, 0), diary_date=TODAY - timedelta(days=200))

    memory = _memory(db, query_vector=_vector(1, 0))

    near = await memory.search(user_id="u-1", query="국밥", period_days=30, max_items=5)
    far = await memory.search(user_id="u-1", query="국밥", period_days=365, max_items=5)

    assert [ref.session_id for ref in near.references] == ["vs-recent"]
    assert {ref.session_id for ref in far.references} == {"vs-recent", "vs-old"}


# --- 3. 세션 집계 -------------------------------------------------------------


@pytest.mark.anyio
async def test_one_session_appears_once(db: AsyncSession) -> None:
    """한 세션에 승인본이 여럿이어도 화면에는 한 번만 나와야 한다."""
    await _seed(db, user_id="u-1", session_id="vs-1", version_id="vv-a",
                embedding=_vector(1, 0))
    db.add(
        DiaryVersion(
            version_id="vv-b", session_id="vs-1", title="제목",
            summary="같은 날의 다른 승인본", content="본문", approved=True,
        )
    )
    await db.flush()
    db.add(DiaryEmbedding(version_id="vv-b", embedding=_vector(0.9, 0.1)))
    await db.flush()

    found = await _memory(db, query_vector=_vector(1, 0)).search(
        user_id="u-1", query="국밥", period_days=30, max_items=5
    )

    assert [ref.session_id for ref in found.references] == ["vs-1"]


# --- 4. 본문은 나가지 않는다 ---------------------------------------------------


@pytest.mark.anyio
async def test_only_the_summary_is_returned(db: AsyncSession) -> None:
    """본문을 실으면 상담이 일기 낭독이 된다."""
    await _seed(db, user_id="u-1", session_id="vs-1", version_id="vv-1",
                embedding=_vector(1, 0), summary="국밥을 먹고 행복했다")

    found = await _memory(db, query_vector=_vector(1, 0)).search(
        user_id="u-1", query="국밥", period_days=30, max_items=5
    )

    reference = found.references[0]
    assert reference.summary == "국밥을 먹고 행복했다"
    assert "본문 전체는" not in reference.model_dump_json()
    assert set(reference.model_dump()) == {
        "session_id", "diary_date", "summary", "emotion_tags", "score"
    }


# --- 5. 빈 질의 ---------------------------------------------------------------


@pytest.mark.anyio
async def test_blank_query_returns_nothing(db: AsyncSession) -> None:
    """검색어가 없다고 아무 일기나 끌어오면 이 기능의 취지가 뒤집힌다."""
    await _seed(db, user_id="u-1", session_id="vs-1", version_id="vv-1",
                embedding=_vector(1, 0))
    embedder = _StubEmbedder(_vector(1, 0))

    found = await VectorDiaryMemory(db, embedder).search(
        user_id="u-1", query="   ", period_days=30, max_items=5
    )

    assert found.references == []
    assert found.top_candidate_score is None
    # 어댑터는 빈 문자열에 ValueError 를 던진다. 부르기 전에 끊어야 한다.
    assert embedder.calls == []


@pytest.mark.anyio
async def test_emotion_is_folded_into_the_query(db: AsyncSession) -> None:
    """벡터는 성분을 나눌 수 없어 감정을 질의 문장에 붙여 함께 인코딩한다."""
    await _seed(db, user_id="u-1", session_id="vs-1", version_id="vv-1",
                embedding=_vector(1, 0))
    embedder = _StubEmbedder(_vector(1, 0))

    await VectorDiaryMemory(db, embedder).search(
        user_id="u-1", query="국밥", period_days=30, max_items=5, emotion="행복"
    )

    assert embedder.calls == ["국밥 행복"]


# --- 6. 임계값 (relevance.lookup 재사용) ---------------------------------------


@pytest.mark.anyio
async def test_a_weak_top_hit_drops_everything(db: AsyncSession) -> None:
    """최상위가 약하면 전부 버린다. 어휘 검색과 같은 규칙을 쓰는지 확인한다."""
    # 질의와 직교하는 벡터 → 코사인 유사도 0
    await _seed(db, user_id="u-1", session_id="vs-1", version_id="vv-1",
                embedding=_vector(0, 1))

    found = await _memory(db, query_vector=_vector(1, 0)).search(
        user_id="u-1", query="국밥", period_days=30, max_items=5
    )

    assert found.references == []
    # 걸러지기 전 점수는 남는다 — 임계값을 옮길 근거가 된다.
    assert found.top_candidate_score is not None
    assert found.top_candidate_score < VectorThresholds().strong_score


@pytest.mark.anyio
async def test_a_strong_hit_passes(db: AsyncSession) -> None:
    await _seed(db, user_id="u-1", session_id="vs-1", version_id="vv-1",
                embedding=_vector(1, 0))

    found = await _memory(db, query_vector=_vector(1, 0)).search(
        user_id="u-1", query="국밥", period_days=30, max_items=5
    )

    assert [ref.session_id for ref in found.references] == ["vs-1"]
    assert found.references[0].score == pytest.approx(1.0, abs=1e-6)


# --- 7. 승인본만 ---------------------------------------------------------------


@pytest.mark.anyio
async def test_drafts_are_not_evidence(db: AsyncSession) -> None:
    """사용자가 고르지 않은 초안을 상담사가 사실처럼 말하면 안 된다.

    어휘 검색(`diary_sql.py`)과 같은 규칙이다.
    """
    await _seed(db, user_id="u-1", session_id="vs-draft", version_id="vv-draft",
                embedding=_vector(1, 0), approved=False)

    found = await _memory(db, query_vector=_vector(1, 0)).search(
        user_id="u-1", query="국밥", period_days=30, max_items=5
    )

    assert found.references == []
