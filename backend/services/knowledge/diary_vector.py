"""과거 일기 검색 (임베딩).

`SqlDiaryMemory`와 같은 자리에 끼우는 두 번째 구현이다. 시그니처가 같아서
`dependencies.py`에서 env 하나로 바꿔 끼운다.

적재는 `services/embedding`이 한다. 여기서는 **읽기만** 한다. 질의 벡터도 적재와
같은 어댑터로 만든다 — 모델이 다르면 두 벡터가 다른 공간에 있어 유사도가
무의미해진다.

`DiaryEmbeddingService.find_similar_diaries`를 쓰지 않는 이유는 그쪽이 사용자와
기간을 가리지 않기 때문이다. 상담 근거로 쓰려면 소유권과 기억 범위(C-03)를
반드시 걸어야 한다.

거르는 규칙은 어휘 검색과 공유한다(`relevance.lookup`). 임계값만 다르다.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.embedding import EmbeddingAdapter
from backend.services.knowledge.base import DiaryLookup, DiaryReference
from backend.services.knowledge.relevance import Candidate, lookup
from backend.services.knowledge.vector_thresholds import VectorThresholds
from database.models import DiaryEmbedding, DiarySession, DiaryVersion


def _normalize_emotion_tags(emotion_tags: Any) -> list[str]:
    """JSON 컬럼에서 읽은 감정 태그를 문자열 목록으로 맞춘다.

    드라이버에 따라 list로도 str로도 온다. `diary_sql`과 같은 처리를 한다.
    """
    if emotion_tags is None:
        return []
    if isinstance(emotion_tags, list):
        return [str(tag) for tag in emotion_tags]
    if isinstance(emotion_tags, str):
        import json

        try:
            parsed = json.loads(emotion_tags)
        except json.JSONDecodeError:
            return [emotion_tags]
        if isinstance(parsed, list):
            return [str(tag) for tag in parsed]
        return [str(parsed)]
    return [str(emotion_tags)]


def _reduce_to_sessions(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """세션당 가장 가까운 한 건만 남긴다.

    한 일기에 승인본이 여럿이면 같은 세션이 여러 번 걸린다. 그대로 두면 화면에
    같은 날 일기가 중복으로 뜨고, max_items 자리도 한 일기가 다 먹는다.

    행은 이미 거리순으로 정렬돼 오므로 먼저 만난 것이 그 세션의 최고점이다.
    """
    best: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        best.setdefault(row["session_id"], row)
    return list(best.values())


def _to_score(distance: Any) -> float:
    """코사인 거리를 0~1 유사도로 바꾼다.

    `DiaryReference.score`가 0~1만 받는다. 반대 방향 벡터는 거리가 1을 넘어
    유사도가 음수로 나오는데, 그대로 넘기면 pydantic 검증에서 턴 전체가
    실패한다. 부동소수 오차로 1을 아주 조금 넘기는 일도 있다.
    """
    return min(max(1.0 - float(distance), 0.0), 1.0)


class VectorDiaryMemory:
    """사용자의 과거 일기 중 지금 대화와 의미가 가까운 것만 돌려준다.

    `DiaryMemoryPort`를 그대로 만족한다 — 흐름(`counsel_flow`)은 어느 구현이
    꽂혔는지 알 필요가 없다.
    """

    def __init__(
        self,
        db: AsyncSession,
        embedder: EmbeddingAdapter,
        *,
        thresholds: VectorThresholds | None = None,
    ) -> None:
        self.db = db
        self._embedder = embedder
        self._thresholds = thresholds or VectorThresholds()

    async def search(
        self,
        *,
        user_id: str,
        query: str,
        period_days: int,
        max_items: int,
        emotion: str | None = None,
    ) -> DiaryLookup:
        if not query.strip():
            # 검색어가 없다고 아무 일기나 끌어오면 이 기능의 취지가 뒤집힌다.
            # 어댑터도 빈 문자열을 거부하므로 부르기 전에 끊는다.
            return DiaryLookup()

        since = date.today() - timedelta(days=max(period_days, 0))

        # 감정은 질의 문장에 붙여 같이 인코딩한다. 어휘 검색처럼 가산점을 따로
        # 매길 수 없다 — 벡터는 통째로 한 점이라 성분을 나눌 수 없다.
        q_text = f"{query} {emotion}".strip() if emotion else query
        qvec = await self._embedder.embed(q_text)

        # 세션당 1건으로 줄이기 전에 넉넉히 가져온다. 한 일기에 승인본이 여럿이면
        # 상위가 같은 세션으로 채워져 max_items 를 못 채운다.
        fanout = max(max_items * 4, max_items)

        # 임베딩 테이블에는 소유자도 날짜도 없다(version_id/embedding/created_at).
        # 소유권과 기억 범위는 diary_versions → diary_sessions 를 타고 건다.
        distance = DiaryEmbedding.embedding.cosine_distance(qvec).label("distance")
        stmt = (
            select(
                DiarySession.session_id,
                DiarySession.diary_date,
                DiaryVersion.summary,
                DiaryVersion.emotion_tags,
                distance,
            )
            .select_from(DiaryEmbedding)
            .join(DiaryVersion, DiaryVersion.version_id == DiaryEmbedding.version_id)
            .join(DiarySession, DiarySession.session_id == DiaryVersion.session_id)
            .where(
                DiarySession.user_id == user_id,  # 소유권은 검색 구현의 책임
                DiarySession.diary_date >= since,  # 기억 범위 C-03
                # 어휘 검색과 같은 규칙이다. 사용자가 고르지 않은 초안을
                # 상담사가 사실처럼 말하면 안 된다.
                DiaryVersion.approved.is_(True),
            )
            .order_by(distance)
            .limit(fanout)
        )
        rows = (await self.db.execute(stmt)).mappings().all()

        candidates = [
            Candidate(
                reference=DiaryReference(
                    session_id=row["session_id"],
                    diary_date=row["diary_date"],
                    # 요약만 싣는다. 본문을 넣으면 상담이 일기 낭독이 된다.
                    summary=row["summary"],
                    emotion_tags=_normalize_emotion_tags(row["emotion_tags"]),
                    score=_to_score(row["distance"]),
                ),
                # 벡터에는 겹친 토큰이라는 개념이 없다. 임계값 쪽에서 두 게이트를
                # 0으로 열어 두므로(`VectorThresholds.as_diary_thresholds`) 여기
                # 값은 통과용 자리채움이다.
                matched=1,
                headline_matched=1,
            )
            for row in _reduce_to_sessions(rows)
        ]

        return lookup(
            candidates,
            self._thresholds.as_diary_thresholds(),
            max_items=max_items,
        )
