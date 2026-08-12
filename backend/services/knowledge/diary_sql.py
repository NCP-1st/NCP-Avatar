"""과거 일기 검색 (실DB).

`diary_sessions` JOIN `diary_versions`에서 **승인된** 일기만 본다. 초안은
사용자가 고르지 않은 글이라 근거로 삼을 수 없다 — 버리기로 한 문장을 상담사가
사실처럼 말하게 된다.

점수와 임계값은 `relevance`가 정한다. 여기서는 후보를 모아 넘기기만 한다.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.knowledge.base import DiaryLookup, DiaryReference
from backend.services.knowledge.relevance import (
    Candidate,
    DiaryThresholds,
    lookup,
    score,
    tokenize,
)
from database.models import DiarySession, DiaryVersion


def _normalize_emotion_tags(emotion_tags: Any) -> list[str]:
    """JSON 컬럼에서 읽은 감정 태그를 문자열 목록으로 맞춘다.

    방언과 드라이버에 따라 list로도 str로도 온다.
    """
    if emotion_tags is None:
        return []
    if isinstance(emotion_tags, list):
        return [str(tag) for tag in emotion_tags]
    if isinstance(emotion_tags, str):
        try:
            parsed = json.loads(emotion_tags)
        except json.JSONDecodeError:
            return [emotion_tags]
        if isinstance(parsed, list):
            return [str(tag) for tag in parsed]
        return [str(parsed)]
    return [str(emotion_tags)]


class SqlDiaryMemory:
    """사용자의 승인된 과거 일기 중 지금 대화와 관련 있는 것만 돌려준다.

    하루에 승인본이 여러 개 남아 있어도 세션당 최신 1건만 본다. 거의 같은
    내용이 근거로 두 번 달리면 사용자에게는 같은 일기가 중복으로 보인다.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        thresholds: DiaryThresholds | None = None,
    ) -> None:
        self.db = db
        self._thresholds = thresholds or DiaryThresholds()

    async def search(
        self,
        *,
        user_id: str,
        query: str,
        period_days: int,
        max_items: int,
        emotion: str | None = None,
    ) -> DiaryLookup:
        # 감정은 따로 둔다 — 분모에 넣으면 토픽이 다 맞은 일기도 탈락한다.
        # `relevance.score` 의 docstring 참고.
        tokens = tokenize(query)
        emotion_tokens = tokenize(emotion)
        if not tokens:
            # 검색어가 없다고 아무 일기나 끌어오면 이 기능의 취지가 뒤집힌다.
            return DiaryLookup()

        since = date.today() - timedelta(days=max(period_days, 0))

        # 세션마다 승인본 중 최신 1건. ix_diary_versions_session_approved_created
        # (session_id, approved, created_at) 를 그대로 탄다.
        #
        # version_id 로 한 번 더 정렬하는 건 동률 때문이다. created_at 은 초
        # 단위라 같은 세션의 승인본 둘이 같은 값을 갖는 일이 실제로 생기고,
        # 그러면 대표가 매번 달라져 같은 질문에 다른 일기를 근거로 대게 된다.
        ranked = (
            sa_select(
                DiaryVersion.session_id,
                DiaryVersion.title,
                DiaryVersion.summary,
                DiaryVersion.content,
                DiaryVersion.emotion_tags,
                func.row_number()
                .over(
                    partition_by=DiaryVersion.session_id,
                    order_by=(
                        DiaryVersion.created_at.desc(),
                        DiaryVersion.version_id.desc(),
                    ),
                )
                .label("rn"),
            )
            .where(DiaryVersion.approved.is_(True))
            .subquery()
        )

        stmt = (
            sa_select(
                DiarySession.session_id,
                DiarySession.diary_date,
                ranked.c.title,
                ranked.c.summary,
                ranked.c.content,
                ranked.c.emotion_tags,
            )
            .join(ranked, ranked.c.session_id == DiarySession.session_id)
            .where(
                DiarySession.user_id == user_id,  # 소유권은 검색 구현의 책임
                DiarySession.diary_date >= since,
                ranked.c.rn == 1,
            )
            .order_by(DiarySession.diary_date.desc())
        )

        # 기간 상한이 365일이라 후보는 최대 그만큼이다. 점수는 파이썬에서
        # 매긴다 — SQL로 옮기면 스텁과 규칙이 갈린다.
        rows = (await self.db.execute(stmt)).all()

        candidates: list[Candidate] = []
        for row in rows:
            tags = _normalize_emotion_tags(row.emotion_tags)

            # 제목·요약·감정태그가 "머리말"이다. 여기 걸리는 게 하나도 없으면
            # 본문에서 아무리 많이 걸려도 근거로 삼지 않는다 —
            # `DiaryThresholds.min_headline_tokens` 의 실측 근거 참고.
            headline = f"{row.title or ''} {row.summary} {' '.join(tags)}"
            _, headline_matched = score(tokens, headline, bonus_tokens=emotion_tokens)

            # 점수는 본문까지 보고 매긴다. 요약 한 문장만으로는 맞출 표면이
            # 너무 좁아서, 같은 이야기를 해도 턴마다 걸렸다 말았다 한다.
            # 본문은 여기까지만 쓰고 프롬프트에는 넣지 않는다.
            value, matched = score(
                tokens,
                f"{headline} {row.content or ''}",
                bonus_tokens=emotion_tokens,
            )
            candidates.append(
                Candidate(
                    reference=DiaryReference(
                        session_id=row.session_id,
                        diary_date=row.diary_date,
                        summary=row.summary,
                        emotion_tags=tags,
                        score=value,
                    ),
                    matched=matched,
                    headline_matched=headline_matched,
                )
            )

        return lookup(candidates, self._thresholds, max_items=max_items)
