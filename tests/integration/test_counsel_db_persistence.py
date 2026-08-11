"""상담 대화 이력이 인메모리 스텁이 아니라 DB에 남는지 검증한다.

세 가지를 본다.
  1. 저장소 계약 — 이력 왕복, 소유권, 위기 플래그 지속, 트레이스 1:1
  2. 흐름 배선 — CounselFlow 가 두 턴을 돌면 DB에 이력과 트레이스가 쌓인다
  3. 마이그레이션 — f1a2c3d4e5f6 이 만드는 스키마가 ORM 모델과 일치한다

운영은 PostgreSQL이지만 테스트는 SQLite 메모리 DB를 쓴다. JSONB·BIGSERIAL은
database/models.py 에서 방언별 variant 로 갈라 둔다.
"""

import importlib.util
import io

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.agents.counsel_chatbot.schemas import (
    ConversationState,
    CounselDraft,
    CounselRequest,
    CounselTrace,
    CounselTurn,
    EmotionReading,
    ExtractedEvent,
    SafetyLevel,
)
from backend.orchestration.counsel_flow import CounselFlow
from backend.repositories import SQLAlchemyConversationStore
from backend.services.knowledge import InMemoryCounselKnowledge, InMemoryPersonalOntology
from database.models import Base, CounselSession, CounselTurnTrace
from database.models import CounselTurn as ORMCounselTurn


@pytest.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _trace(trace_id: str = "trace-1", **overrides: object) -> CounselTrace:
    fields: dict[str, object] = {
        "trace_id": trace_id,
        "model": "HCX-005",
        "latency_ms": 120,
        "result_code": "ok",
        "stage": "opening",
        "emotion": "불안",
        "knowledge_count": 2,
        "ontology_count": 1,
        "event_count": 1,
        "guardrail_hits": [],
        "stage_ms": {"context": 30, "counselor": 90},
    }
    fields.update(overrides)
    return CounselTrace(**fields)  # type: ignore[arg-type]


# --- 1. 저장소 계약 ---------------------------------------------------------


@pytest.mark.anyio
async def test_turns_survive_in_the_database(db: AsyncSession) -> None:
    """이력은 클라이언트가 아니라 서버가 보관한다."""
    store = SQLAlchemyConversationStore(db)

    assert await store.load_turns(counsel_id="c-1", user_id="u-1") == []

    await store.append_turn(
        counsel_id="c-1",
        user_id="u-1",
        turn=CounselTurn(role="user", content="요즘 잠이 안 와요"),
    )
    await store.append_turn(
        counsel_id="c-1",
        user_id="u-1",
        turn=CounselTurn(role="assistant", content="언제부터 그러셨어요?", stage="opening"),
        safety_level="normal",
    )

    turns = await store.load_turns(counsel_id="c-1", user_id="u-1")
    assert [turn.role for turn in turns] == ["user", "assistant"]
    assert turns[0].content == "요즘 잠이 안 와요"
    # _decide_stage 가 직전 어시스턴트 턴의 stage 를 읽으므로 반드시 남아야 한다.
    assert turns[1].stage == "opening"
    assert turns[0].stage is None


@pytest.mark.anyio
async def test_load_turns_returns_the_recent_window_oldest_first(db: AsyncSession) -> None:
    store = SQLAlchemyConversationStore(db)
    for index in range(5):
        await store.append_turn(
            counsel_id="c-1",
            user_id="u-1",
            turn=CounselTurn(role="user", content=f"message-{index}"),
        )

    recent = await store.load_turns(counsel_id="c-1", user_id="u-1", limit=3)

    assert [turn.content for turn in recent] == ["message-2", "message-3", "message-4"]


@pytest.mark.anyio
async def test_another_user_cannot_read_or_write_the_session(db: AsyncSession) -> None:
    """남의 counsel_id 를 찍어 대화를 읽어가는 걸 저장소가 막는다."""
    store = SQLAlchemyConversationStore(db)
    await store.append_turn(
        counsel_id="c-1",
        user_id="u-1",
        turn=CounselTurn(role="user", content="비밀 이야기"),
    )

    assert await store.load_turns(counsel_id="c-1", user_id="attacker") == []

    with pytest.raises(PermissionError):
        await store.append_turn(
            counsel_id="c-1",
            user_id="attacker",
            turn=CounselTurn(role="user", content="끼어들기"),
        )


@pytest.mark.anyio
async def test_crisis_flag_persists_on_the_session(db: AsyncSession) -> None:
    """한 번 켜진 위기 표시는 세션 내내 유지된다."""
    store = SQLAlchemyConversationStore(db)
    await store.append_turn(
        counsel_id="c-1",
        user_id="u-1",
        turn=CounselTurn(role="user", content="안녕하세요"),
    )
    assert await store.is_crisis(counsel_id="c-1", user_id="u-1") is False

    await store.mark_crisis(counsel_id="c-1", user_id="u-1")

    assert await store.is_crisis(counsel_id="c-1", user_id="u-1") is True
    assert await store.is_crisis(counsel_id="c-1", user_id="attacker") is False

    session = await db.get(CounselSession, "c-1")
    assert session is not None and session.is_crisis is True
    assert session.safety_level == "crisis"


@pytest.mark.anyio
async def test_session_safety_level_never_drops_back(db: AsyncSession) -> None:
    """세션 등급은 도달한 최고 등급의 롤업이다. 화제를 돌려도 내려오지 않는다."""
    store = SQLAlchemyConversationStore(db)
    await store.mark_crisis(counsel_id="c-1", user_id="u-1")

    await store.append_turn(
        counsel_id="c-1",
        user_id="u-1",
        turn=CounselTurn(role="assistant", content="계속 들을게요", stage="exploring"),
        safety_level="normal",
    )

    session = await db.get(CounselSession, "c-1")
    assert session is not None and session.safety_level == "crisis"


@pytest.mark.anyio
async def test_trace_is_stored_with_the_assistant_turn(db: AsyncSession) -> None:
    """어시스턴트 턴 1건 : 트레이스 1행."""
    store = SQLAlchemyConversationStore(db)
    await store.append_turn(
        counsel_id="c-1",
        user_id="u-1",
        turn=CounselTurn(role="assistant", content="더 들려주세요", stage="opening"),
        trace=_trace(),
        safety_level="caution",
    )

    stored = (await db.execute(select(CounselTurnTrace))).scalars().all()
    turns = (await db.execute(select(ORMCounselTurn))).scalars().all()

    assert len(stored) == 1
    assert stored[0].turn_id == turns[0].turn_id
    assert stored[0].trace_id == "trace-1"
    assert stored[0].model == "HCX-005"
    assert stored[0].stage_ms == {"context": 30, "counselor": 90}
    # 세션 롤업이 아니라 이번 턴의 등급이 남아야 사후 리뷰가 정확하다.
    assert stored[0].safety_level == "caution"


@pytest.mark.anyio
async def test_crisis_turns_are_queryable_for_review(db: AsyncSession) -> None:
    """result_code / safety_level 로 사후 리뷰 큐를 뽑을 수 있다."""
    store = SQLAlchemyConversationStore(db)
    await store.append_turn(
        counsel_id="c-1",
        user_id="u-1",
        turn=CounselTurn(role="assistant", content="평범한 답변", stage="exploring"),
        trace=_trace("trace-ok"),
        safety_level="normal",
    )
    await store.append_turn(
        counsel_id="c-2",
        user_id="u-1",
        turn=CounselTurn(role="assistant", content="안전 안내"),
        trace=_trace("trace-crisis", result_code="crisis_redirect", stage=None),
        safety_level="crisis",
    )

    queue = (
        await db.execute(
            select(CounselTurnTrace).where(
                (CounselTurnTrace.result_code == "crisis_redirect")
                | (CounselTurnTrace.safety_level == "crisis")
            )
        )
    ).scalars().all()

    assert [row.trace_id for row in queue] == ["trace-crisis"]


# --- 2. 흐름 배선 -----------------------------------------------------------


class _StubContextAgent:
    async def structure(self, message: str, history: list[CounselTurn]) -> ConversationState:
        return ConversationState(
            events=[ExtractedEvent(summary="야근이 이어짐", people=[], place=None, when_hint="요즘")],
            emotion=EmotionReading(
                primary="피로", secondary=[], intensity=3, confidence=0.8, evidence="지쳐요"
            ),
            topics=["야근", "피로"],
            situation_clear=False,
            unclear_point="언제부터 그랬는지",
            wants_closure=False,
        )


class _StubCounselorAgent:
    model = "stub-model"

    # 같은 문장을 두 턴 연속 쓰면 style 검사에 걸려 재생성이 돈다. 실제 상담사처럼
    # 매 턴 다르게 답해서 이 테스트가 DB 배선만 보도록 한다.
    _REPLIES = (
        ("많이 지치셨겠어요.", "언제부터 그러셨어요?"),
        ("계속 그런 상태였군요.", "그때 어떤 생각이 드셨어요?"),
        ("그러셨군요.", "요즘은 어떻게 지내세요?"),
    )

    def __init__(self) -> None:
        self.calls = 0

    async def draft(self, **kwargs: object) -> CounselDraft:
        reply, question = self._REPLIES[self.calls % len(self._REPLIES)]
        self.calls += 1
        return CounselDraft(
            reply=reply,
            question=question,
            summary=None,
            suggestion=None,
            suggestion_kind=None,
        )


def _flow(store: SQLAlchemyConversationStore) -> CounselFlow:
    return CounselFlow(
        context_agent=_StubContextAgent(),  # type: ignore[arg-type]
        counselor_agent=_StubCounselorAgent(),  # type: ignore[arg-type]
        knowledge=InMemoryCounselKnowledge(),
        ontology=InMemoryPersonalOntology(),
        store=store,
    )


@pytest.mark.anyio
async def test_second_call_sees_the_first_conversation(db: AsyncSession) -> None:
    """두 번째 호출에서 이전 대화가 이력으로 들어온다 (README 체크리스트)."""
    store = SQLAlchemyConversationStore(db)
    flow = _flow(store)

    first = await flow.run(CounselRequest(user_id="u-1", message="요즘 너무 지쳐요"))
    second = await flow.run(
        CounselRequest(user_id="u-1", message="야근이 계속돼서요", counsel_id=first.counsel_id)
    )

    assert second.counsel_id == first.counsel_id
    stored = await store.load_turns(counsel_id=first.counsel_id, user_id="u-1")
    assert [turn.content for turn in stored[:3]] == [
        "요즘 너무 지쳐요",
        "많이 지치셨겠어요.\n\n언제부터 그러셨어요?",
        "야근이 계속돼서요",
    ]
    # 첫 턴은 opening, 이력이 쌓인 두 번째 턴은 exploring 으로 올라간다.
    assert [turn.stage for turn in stored if turn.role == "assistant"] == [
        "opening",
        "exploring",
    ]


@pytest.mark.anyio
async def test_flow_writes_one_trace_per_assistant_turn(db: AsyncSession) -> None:
    store = SQLAlchemyConversationStore(db)
    flow = _flow(store)

    reply = await flow.run(CounselRequest(user_id="u-1", message="요즘 너무 지쳐요"))

    traces = (await db.execute(select(CounselTurnTrace))).scalars().all()
    assert len(traces) == 1
    assert traces[0].trace_id == reply.trace.trace_id
    assert traces[0].model == "stub-model"
    assert traces[0].safety_level == "normal"
    assert traces[0].emotion == "피로"
    assert traces[0].stage == "opening"


@pytest.mark.anyio
async def test_crisis_blocks_the_suggestion_path_on_later_turns(db: AsyncSession) -> None:
    """위기 뒤에 화제를 돌려도 정리·제안 단계로 올라가지 않는다."""
    store = SQLAlchemyConversationStore(db)
    flow = _flow(store)

    crisis = await flow.run(
        CounselRequest(user_id="u-1", message="오늘 다 끝낼 생각이에요")
    )
    assert crisis.safety_level is SafetyLevel.CRISIS
    assert crisis.trace.result_code == "crisis_redirect"

    session = await db.get(CounselSession, crisis.counsel_id)
    assert session is not None and session.is_crisis is True

    # 화제를 돌린 다음 턴 — 제안이 열리면 안 된다.
    for message in ("그건 그렇고 점심 뭐 먹을까요", "날씨가 좋네요"):
        follow_up = await flow.run(
            CounselRequest(user_id="u-1", message=message, counsel_id=crisis.counsel_id)
        )
        assert follow_up.stage is not None and follow_up.stage.value == "exploring"
        assert follow_up.sections is not None
        assert follow_up.sections.suggestion is None

    traces = (await db.execute(select(CounselTurnTrace))).scalars().all()
    assert [row.result_code for row in traces] == ["crisis_redirect", "ok", "ok"]
    assert traces[0].safety_level == "crisis"


@pytest.mark.anyio
async def test_chat_endpoint_persists_history_across_requests(db: AsyncSession) -> None:
    """POST /api/counsel/chat 두 번 — 두 번째 요청이 첫 대화를 이력으로 본다.

    요청 스코프 DB 세션이 저장소까지 내려오는지(dependencies.py 배선) 본다.
    에이전트만 스텁으로 갈아끼우고 저장소 경로는 그대로 쓴다.
    """
    from fastapi.testclient import TestClient

    from backend.api.counsel import router
    from backend.dependencies import get_counsel_flow, get_counsel_store
    from database.conn.db import get_db
    from fastapi import Depends, FastAPI
    from typing import Annotated

    def _stub_flow(
        store: Annotated[SQLAlchemyConversationStore, Depends(get_counsel_store)],
    ) -> CounselFlow:
        return _flow(store)

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_counsel_flow] = _stub_flow

    with TestClient(app) as client:
        first = client.post(
            "/api/counsel/chat", json={"user_id": "u-1", "message": "요즘 너무 지쳐요"}
        )
        assert first.status_code == 200, first.text
        counsel_id = first.json()["counsel_id"]

        second = client.post(
            "/api/counsel/chat",
            json={
                "user_id": "u-1",
                "message": "야근이 계속돼서요",
                "counsel_id": counsel_id,
            },
        )
        assert second.status_code == 200, second.text

    assert second.json()["counsel_id"] == counsel_id
    stored = (await db.execute(select(ORMCounselTurn))).scalars().all()
    assert [row.content for row in stored][:3] == [
        "요즘 너무 지쳐요",
        "많이 지치셨겠어요.\n\n언제부터 그러셨어요?",
        "야근이 계속돼서요",
    ]
    # 두 번째 턴이 opening 이 아니라 exploring — 이력을 실제로 읽었다는 뜻이다.
    assert [row.stage for row in stored if row.role == "assistant"] == [
        "opening",
        "exploring",
    ]


@pytest.mark.anyio
async def test_chat_endpoint_rejects_another_users_session(db: AsyncSession) -> None:
    """남의 counsel_id 로 끼어들면 500(서버 장애)이 아니라 403(거절)."""
    from fastapi.testclient import TestClient

    from backend.api.counsel import router
    from backend.dependencies import get_counsel_flow, get_counsel_store
    from database.conn.db import get_db
    from fastapi import Depends, FastAPI
    from typing import Annotated

    def _stub_flow(
        store: Annotated[SQLAlchemyConversationStore, Depends(get_counsel_store)],
    ) -> CounselFlow:
        return _flow(store)

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_counsel_flow] = _stub_flow

    with TestClient(app) as client:
        owned = client.post(
            "/api/counsel/chat", json={"user_id": "u-1", "message": "요즘 너무 지쳐요"}
        )
        counsel_id = owned.json()["counsel_id"]

        stolen = client.post(
            "/api/counsel/chat",
            json={
                "user_id": "attacker",
                "message": "남의 대화 훔쳐보기",
                "counsel_id": counsel_id,
            },
        )

    assert stolen.status_code == 403
    # 세션 존재 여부를 알려주지 않는다.
    assert "attacker" not in stolen.text

    # 거절된 요청은 아무것도 남기지 않는다.
    await db.rollback()
    turns = (await db.execute(select(ORMCounselTurn))).scalars().all()
    assert [row.user_id for row in turns] == ["u-1", "u-1"]


# --- 3. 마이그레이션 --------------------------------------------------------


def _migration_sql() -> str:
    """f1a2c3d4e5f6 의 upgrade() 를 PostgreSQL 대상 SQL 로 뽑는다."""
    spec = importlib.util.spec_from_file_location(
        "counsel_migration",
        "database/migrations/versions/f1a2c3d4e5f6_counsel_turns_and_traces.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    buffer = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buffer}
    )
    with Operations.context(context):
        module.upgrade()
    return buffer.getvalue()


@pytest.mark.parametrize(
    "table", ["counsel_turns", "counsel_turn_traces", "counsel_evidences"]
)
def test_migration_creates_the_same_columns_as_the_orm(table: str) -> None:
    """마이그레이션과 ORM 이 갈라지면 운영에서만 터진다. 여기서 잡는다."""
    sql = _migration_sql()
    start = sql.index(f"CREATE TABLE {table} (")
    body = sql[sql.index("(", start) + 1 : sql.index("\n);", start)]

    migrated = {
        line.strip().split()[0]
        for line in body.splitlines()
        if line.strip()
        and not line.strip().startswith(
            ("PRIMARY KEY", "FOREIGN KEY", "CONSTRAINT", "UNIQUE")
        )
    }

    assert migrated == {column.name for column in Base.metadata.tables[table].columns}


def test_migrations_have_a_single_head() -> None:
    """머지로 head 가 갈라지면 `alembic upgrade head` 가 아예 못 돈다.

    counsel 마이그레이션은 일기 쪽 head 위에 올라간다. 두 갈래가 같은 부모에서
    갈라지면 여기서 걸린다 — 배포할 때 말고.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert len(script.get_heads()) == 1, (
        f"head 가 여러 개다: {script.get_heads()}. "
        "새 마이그레이션의 down_revision 을 현재 head 로 다시 연결해야 한다."
    )


def test_migration_adds_every_new_counsel_session_column() -> None:
    sql = _migration_sql()
    added = {
        line.split("ADD COLUMN ")[1].split()[0]
        for line in sql.splitlines()
        if "ALTER TABLE counsel_sessions ADD COLUMN" in line
    }

    assert added == {
        "title",
        "is_crisis",
        "memory_enabled",
        "memory_period_days",
        "memory_max_items",
        "last_active_at",
    }
