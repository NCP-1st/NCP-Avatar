"""개발용 온톨로지 스텁.

실제 지식베이스·그래프 DB가 붙기 전까지 흐름을 돌려보기 위한 것이다. 샘플
데이터는 형식을 보여주는 최소한이며 상담 근거로 쓸 수준이 아니다.
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.services.knowledge.base import (
    DiaryLookup,
    DiaryReference,
    OntologyFact,
)
from backend.services.knowledge.relevance import (
    Candidate,
    DiaryThresholds,
    lookup,
    score,
    tokenize,
)


class InMemoryPersonalOntology:
    """인물·장소 이름이 겹치는 관계를 돌려주는 스텁."""

    def __init__(self, facts: list[OntologyFact] | None = None) -> None:
        # 개인 관계는 사용자의 실제 기록에서 주입된 사실만 사용한다.
        self._facts = list(facts) if facts is not None else []

    async def related(
        self,
        *,
        user_id: str,
        entities: list[str],
        max_items: int = 5,
    ) -> list[OntologyFact]:
        if not entities:
            return []
        wanted = set(entities)
        matched = [
            fact
            for fact in self._facts
            if fact.subject in wanted or fact.object in wanted
        ]
        # 관찰된 사실을 추론보다 앞에 둔다.
        matched.sort(key=lambda fact: fact.observed, reverse=True)
        return matched[:max_items]


class InMemoryDiaryMemory:
    """일기 검색 스텁. 주입한 것만 본다.

    기본값이 빈 목록인 것은 의도한 바다. 없는 일기를 지어내면 상담이 사용자의
    과거를 꾸며내게 된다. 실제 조회는 `SqlDiaryMemory`가 한다.

    점수와 임계값은 SQL 구현과 같은 규칙(`relevance`)을 쓴다. 여기서만 느슨하게
    두면 스텁으로 통과한 테스트가 실제 DB에서 다르게 동작한다.
    """

    def __init__(
        self,
        entries: list[DiaryReference] | None = None,
        *,
        thresholds: DiaryThresholds | None = None,
    ) -> None:
        self._entries = list(entries) if entries is not None else []
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
        tokens = tokenize(query)
        emotion_tokens = tokenize(emotion)
        if not tokens:
            return DiaryLookup()

        since = date.today() - timedelta(days=period_days)
        candidates: list[Candidate] = []
        for entry in self._entries:
            if entry.diary_date < since:
                continue
            # 스텁이 들고 있는 `DiaryReference`에는 본문이 없다. 그래서 머리말과
            # 전체가 같다 — 본문에만 걸리는 경우가 없으니 `min_headline_tokens`가
            # 여기서는 항상 통과한다. 그 규칙은 SQL 구현에서만 의미가 있다.
            haystack = f"{entry.summary} {' '.join(entry.emotion_tags)}"
            value, matched = score(tokens, haystack, bonus_tokens=emotion_tokens)
            candidates.append(
                Candidate(
                    reference=entry.model_copy(update={"score": value}),
                    matched=matched,
                    headline_matched=matched,
                )
            )

        return lookup(candidates, self._thresholds, max_items=max_items)

