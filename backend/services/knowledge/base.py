"""온톨로지 검색(RAG) 인터페이스.

두 종류를 나눠 둔다. 섞으면 "일반 상담 지식"과 "이 사용자에 대한 사실"이 한
덩어리로 프롬프트에 들어가, 모델이 일반론을 사용자 개인사인 것처럼 말한다.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class KnowledgeSnippet(BaseModel):
    """상담 지식베이스에서 찾은 조각.

    답변에 그대로 인용하지 않는다. 상담가 에이전트가 말투를 잡는 참고로만
    쓰고, 사용자에게는 출처를 노출하지 않는다.
    """

    snippet_id: str
    title: str
    content: str = Field(max_length=600)
    source: str  # 가이드라인 문서명·조항
    score: float = Field(default=0.0, ge=0, le=1)


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


class CounselKnowledgePort(Protocol):
    """상담 기법·가이드라인·위기 대응 규칙 검색 (사용자 무관)."""

    async def search(
        self,
        *,
        query: str,
        emotion: str | None = None,
        top_k: int = 3,
    ) -> list[KnowledgeSnippet]:
        ...


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
