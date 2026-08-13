"""온톨로지 검색(RAG) 인터페이스.

두 종류를 나눠 둔다. 섞으면 "이 사용자가 쓴 일기"와 "이 사용자에 대해 추론한
사실"이 한 덩어리로 프롬프트에 들어가, 모델이 추론을 기록인 것처럼 말한다.

일반 상담 지식(상담 기법)은 여기 없다. 검색으로 고르던 것을 프롬프트 정적
블록으로 옮겼다 — 감정 라벨이 닫힌 목록이고 단계도 흐름이 이미 아는 값이라,
아는 것을 의미 유사도로 다시 맞히는 셈이었다. `prompts.py` 참고.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from pydantic import BaseModel, Field


class OntologyFact(BaseModel):
    """개인 온톨로지에서 찾은 관계 한 줄.

    `observed`로 관찰된 사실과 추론을 구분한다. 추론을 사실처럼 말하면
    H-02(근거 제시)를 어기게 되므로, 프롬프트에도 이 구분을 넘긴다.
    """

    subject: str
    relation: str
    object: str
    observed: bool = True  # False면 기록에서 추론한 것
    evidence_diary_ids: list[str] = Field(default_factory=list)


class DiaryReference(BaseModel):
    """사용자가 직접 쓴 과거 일기 한 건의 요약.

    본문(`DiaryVersion.content`)은 담지 않는다. 전문을 프롬프트에 부으면 상담이
    일기 낭독이 되고, 모델이 원문을 그대로 인용하게 된다. 발췌도 넣지 않는다 —
    잘라 넣어도 원문 문장인 건 같아서 인용이 되기는 마찬가지다.

    담는 것은 사용자가 이미 승인한 요약 층까지다. `title`·`summary`·
    `emotion_tags` 셋이면 "그때 무슨 일이 있었고 어떤 마음이었나"를 짚을 수
    있고, 그게 날짜만 대는 것과 구체적으로 이어주는 것의 차이다.

    `diary_date`는 H-02 근거 카드와 `counsel_evidences.diary_date`가 쓴다.
    원본 일기가 지워져도 무엇을 근거로 삼았는지는 남아야 한다.
    """

    session_id: str
    diary_date: date
    # 검색 구현이 채운다. 옛 데이터나 스텁에서 비어 올 수 있어 None을 허용한다.
    title: str | None = None
    summary: str
    emotion_tags: list[str] = Field(default_factory=list)
    score: float = Field(default=0.0, ge=0, le=1)


class DiaryLookup(BaseModel):
    """일기 검색 한 번의 결과.

    `references`만으로는 임계값을 조정할 수 없다. 참조에 실패한 턴이 아깝게
    떨어진 것인지(0.67) 아예 무관한 것인지(0.0) 구별이 안 되는데, 임계값을
    옮길지 말지는 **바로 그 분포**가 정한다. 그래서 걸러지기 전 최고점을 같이
    들고 나온다.

    `top_candidate_score`는 관측용이다. 프롬프트에도 화면에도 쓰지 않는다.
    후보가 아예 없었으면(기간 안에 승인된 일기가 없음) None이다.
    """

    references: list[DiaryReference] = Field(default_factory=list)
    top_candidate_score: float | None = Field(default=None, ge=0, le=1)


class PersonalOntologyPort(Protocol):
    """이 사용자의 인물·장소·사건 관계 조회 (동의 범위 안).

    `entities`는 이번 대화에서 뽑은 인물·장소다. 동의 범위 밖 데이터는
    구현체가 걸러서 돌려줘야 한다.
    """

    async def related(
        self,
        *,
        user_id: str,
        entities: list[str],
        max_items: int = 5,
    ) -> list[OntologyFact]:
        ...


class DiaryMemoryPort(Protocol):
    """이 사용자의 과거 일기 검색 (동의·기억 범위 안). 관련도 낮으면 빈 결과.

    **관련도 판정은 구현체의 책임이다.** 애매한 후보까지 돌려주고 흐름 쪽에서
    거르게 하면, 검색 구현을 바꿀 때마다 흐름의 임계값도 같이 손봐야 한다.
    `references`에 담아 돌려준 것은 프롬프트에 들어간다고 보면 된다.

    소유권도 구현체가 지킨다 — `user_id`의 일기만 돌려줘야 한다.
    """

    async def search(
        self,
        *,
        user_id: str,
        query: str,
        period_days: int,
        max_items: int,
        emotion: str | None = None,
    ) -> DiaryLookup:
        ...
