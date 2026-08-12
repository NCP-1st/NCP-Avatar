"""지난 상담 목록·이력 조회.

이 기능이 붙기 전에는 대화가 DB에 쌓이기만 하고 꺼낼 길이 없었다. 프런트가
`counsel_id`를 브라우저 세션에만 들고 있어서 새로고침 한 번에 영구 소실됐다.

여기서 지키는 것은 셋이다.
- 남의 상담이 목록에도 이력에도 나오지 않는다
- 새로고침 뒤에도 근거 표시(H-02)가 남는다
- 지난 상담을 이어서 계속할 수 있다
"""

from datetime import date, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.agents.counsel_chatbot.schemas import CounselTrace, CounselTurn
from backend.main import app
from backend.repositories import InMemoryConversationStore, SQLAlchemyConversationStore
from backend.repositories.base import title_from_message
from backend.services.knowledge.base import DiaryReference
from database.conn.db import get_db
from database.models import Base, DiarySession, DiaryVersion, User

TODAY = date.today()


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


@pytest.fixture
async def client(db: AsyncSession) -> AsyncClient:
    async def override_get_db():
        yield db

    # `clear()` 로 끝내면 안 된다. `test_preprocessing.py` 는 모듈을 읽는
    # 시점에 자기 오버라이드를 걸어 두는데, 여기서 통째로 지우면 그쪽
    # TestClient 가 실 DB 로 떨어져 엉뚱한 곳에서 asyncpg 오류가 난다.
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def _trace() -> CounselTrace:
    return CounselTrace(
        trace_id="t-1", model="stub", latency_ms=1, result_code="ok", stage="exploring"
    )


async def _seed_conversation(
    db: AsyncSession,
    *,
    counsel_id: str,
    user_id: str,
    messages: list[str],
    diary_refs: list[DiaryReference] | None = None,
) -> None:
    store = SQLAlchemyConversationStore(db)
    for index, message in enumerate(messages):
        await store.append_turn(
            counsel_id=counsel_id,
            user_id=user_id,
            turn=CounselTurn(role="user", content=message),
        )
        await store.append_turn(
            counsel_id=counsel_id,
            user_id=user_id,
            turn=CounselTurn(role="assistant", content=f"답변 {index}", stage="exploring"),
            trace=_trace(),
            # 근거는 마지막 답변에만 붙인다.
            diary_refs=diary_refs if index == len(messages) - 1 else None,
        )


async def _seed_diary(db: AsyncSession) -> DiaryReference:
    db.add(DiarySession(session_id="d-1", user_id="u-1", diary_date=TODAY))
    await db.flush()
    db.add(
        DiaryVersion(
            version_id="v-1", session_id="d-1", title="국밥",
            summary="국밥을 먹고 행복했다", content="본문", approved=True,
        )
    )
    await db.commit()
    return DiaryReference(
        session_id="d-1", diary_date=TODAY, summary="국밥을 먹고 행복했다", score=1.0
    )


# --- 1. 목록 ----------------------------------------------------------------


@pytest.mark.anyio
async def test_sessions_are_listed_most_recent_first(db: AsyncSession) -> None:
    await _seed_conversation(db, counsel_id="c-1", user_id="u-1", messages=["첫 대화"])
    await _seed_conversation(db, counsel_id="c-2", user_id="u-1", messages=["나중 대화"])

    listed = await SQLAlchemyConversationStore(db).list_sessions(user_id="u-1")

    assert [item.counsel_id for item in listed] == ["c-2", "c-1"]


@pytest.mark.anyio
async def test_title_comes_from_the_first_user_message(db: AsyncSession) -> None:
    """제목은 첫 마디에서 만든다. 저장된 title 이 없는 기존 세션도 나와야 한다."""
    await _seed_conversation(
        db, counsel_id="c-1", user_id="u-1",
        messages=["요즘 회사 일 때문에 지쳐요", "두 번째로 한 말"],
    )

    listed = await SQLAlchemyConversationStore(db).list_sessions(user_id="u-1")

    assert listed[0].title == "요즘 회사 일 때문에 지쳐요"
    assert listed[0].turn_count == 4  # 사용자 2 + 어시스턴트 2


@pytest.mark.anyio
async def test_another_users_sessions_never_appear(db: AsyncSession) -> None:
    await _seed_conversation(db, counsel_id="c-mine", user_id="u-1", messages=["내 대화"])
    await _seed_conversation(db, counsel_id="c-theirs", user_id="u-2", messages=["남의 대화"])

    listed = await SQLAlchemyConversationStore(db).list_sessions(user_id="u-1")

    assert [item.counsel_id for item in listed] == ["c-mine"]


@pytest.mark.anyio
async def test_empty_sessions_are_not_listed(db: AsyncSession) -> None:
    """첫 요청이 실패하면 턴 없는 세션이 남는다. 목록에 빈 줄이 쌓이면 안 된다."""
    from database.models import CounselSession

    db.add(User(user_id="u-1"))
    db.add(CounselSession(counsel_id="c-empty", user_id="u-1"))
    await db.commit()

    listed = await SQLAlchemyConversationStore(db).list_sessions(user_id="u-1")

    assert listed == []


@pytest.mark.anyio
async def test_crisis_sessions_are_flagged(db: AsyncSession) -> None:
    """위기가 있었던 대화는 목록에서 구분되어야 한다."""
    store = SQLAlchemyConversationStore(db)
    await _seed_conversation(db, counsel_id="c-1", user_id="u-1", messages=["힘들어요"])
    await store.mark_crisis(counsel_id="c-1", user_id="u-1")

    listed = await store.list_sessions(user_id="u-1")

    assert listed[0].is_crisis is True
    assert listed[0].safety_level == "crisis"


# --- 2. 이력 ----------------------------------------------------------------


@pytest.mark.anyio
async def test_history_returns_the_whole_conversation_in_order(db: AsyncSession) -> None:
    """`load_turns` 와 달리 최근 N개로 자르지 않는다. 읽던 대화의 중간이
    잘리면 안 된다."""
    messages = [f"메시지 {i}" for i in range(15)]
    await _seed_conversation(db, counsel_id="c-1", user_id="u-1", messages=messages)

    history = await SQLAlchemyConversationStore(db).load_history(
        counsel_id="c-1", user_id="u-1"
    )

    assert len(history.turns) == 30
    assert history.turns[0].content == "메시지 0"
    assert history.turns[0].role == "user"
    assert history.turns[-1].role == "assistant"


@pytest.mark.anyio
async def test_history_keeps_the_evidence_after_a_reload(db: AsyncSession) -> None:
    """H-02. 새로고침에 근거 표시가 사라지면 상담사가 과거를 어떻게 알았는지
    확인할 방법이 없어진다."""
    reference = await _seed_diary(db)
    await _seed_conversation(
        db, counsel_id="c-1", user_id="u-1",
        messages=["국밥 얘기"], diary_refs=[reference],
    )

    history = await SQLAlchemyConversationStore(db).load_history(
        counsel_id="c-1", user_id="u-1"
    )

    assistant = [turn for turn in history.turns if turn.role == "assistant"]
    assert [ref.diary_date for ref in assistant[-1].evidences] == [TODAY]
    assert assistant[-1].evidences[0].session_id == "d-1"
    # 근거가 없는 턴에 남의 근거가 새어 들어가면 안 된다.
    assert [turn for turn in history.turns if turn.role == "user"][0].evidences == []


@pytest.mark.anyio
async def test_history_of_another_user_is_refused(db: AsyncSession) -> None:
    await _seed_conversation(db, counsel_id="c-1", user_id="u-1", messages=["내 대화"])

    with pytest.raises(PermissionError):
        await SQLAlchemyConversationStore(db).load_history(
            counsel_id="c-1", user_id="u-2"
        )


@pytest.mark.anyio
async def test_missing_session_is_refused_the_same_way(db: AsyncSession) -> None:
    """없는 상담과 남의 상담을 구분해 주면 counsel_id 를 훑어 존재 여부를
    알아낼 수 있다."""
    with pytest.raises(PermissionError):
        await SQLAlchemyConversationStore(db).load_history(
            counsel_id="c-nope", user_id="u-1"
        )


# --- 3. HTTP ----------------------------------------------------------------


@pytest.mark.anyio
async def test_endpoints_serve_the_list_and_the_history(
    db: AsyncSession, client: AsyncClient
) -> None:
    reference = await _seed_diary(db)
    await _seed_conversation(
        db, counsel_id="c-1", user_id="u-1",
        messages=["요즘 국밥만 먹어요"], diary_refs=[reference],
    )

    listed = await client.get("/api/counsel/sessions", params={"user_id": "u-1"})
    assert listed.status_code == 200
    assert listed.json()[0]["title"] == "요즘 국밥만 먹어요"

    history = await client.get(
        "/api/counsel/sessions/c-1", params={"user_id": "u-1"}
    )
    assert history.status_code == 200
    body = history.json()
    assert body["counsel_id"] == "c-1"
    assert body["turns"][-1]["evidences"][0]["diary_date"] == TODAY.isoformat()


@pytest.mark.anyio
async def test_endpoint_refuses_another_users_history(
    db: AsyncSession, client: AsyncClient
) -> None:
    await _seed_conversation(db, counsel_id="c-1", user_id="u-1", messages=["내 대화"])

    response = await client.get(
        "/api/counsel/sessions/c-1", params={"user_id": "attacker"}
    )

    assert response.status_code == 403
    # 세션이 있는지 없는지 알려주지 않는다.
    assert "c-1" not in response.text


@pytest.mark.anyio
async def test_endpoint_hides_other_users_from_the_list(
    db: AsyncSession, client: AsyncClient
) -> None:
    await _seed_conversation(db, counsel_id="c-theirs", user_id="u-2", messages=["남의 것"])

    response = await client.get(
        "/api/counsel/sessions", params={"user_id": "u-1"}
    )

    assert response.status_code == 200
    assert response.json() == []


# --- 4. 스텁 ----------------------------------------------------------------


@pytest.mark.anyio
async def test_in_memory_stub_matches_the_contract() -> None:
    """스텁이 다르게 동작하면 스텁으로 통과한 테스트가 실제 DB에서 깨진다."""
    store = InMemoryConversationStore()
    await store.append_turn(
        counsel_id="c-1", user_id="u-1",
        turn=CounselTurn(role="user", content="요즘 회사 일 때문에 지쳐요"),
    )

    listed = await store.list_sessions(user_id="u-1")
    assert [item.title for item in listed] == ["요즘 회사 일 때문에 지쳐요"]
    assert await store.list_sessions(user_id="u-2") == []

    history = await store.load_history(counsel_id="c-1", user_id="u-1")
    assert [turn.content for turn in history.turns] == ["요즘 회사 일 때문에 지쳐요"]

    with pytest.raises(PermissionError):
        await store.load_history(counsel_id="c-1", user_id="u-2")


# --- 5. 제목 만들기 ---------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("짧은 말", "짧은 말"),
        ("  공백은   정리한다  ", "공백은 정리한다"),
        (None, "제목 없는 대화"),
        ("", "제목 없는 대화"),
    ],
)
def test_title_rules(message: str | None, expected: str) -> None:
    assert title_from_message(message) == expected


def test_long_titles_are_cut_with_an_ellipsis() -> None:
    title = title_from_message("가" * 100)

    assert len(title) == 30
    assert title.endswith("…")
