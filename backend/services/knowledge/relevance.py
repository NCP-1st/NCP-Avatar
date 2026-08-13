"""일기 후보의 관련도 점수와 임계값 필터.

검색 구현(인메모리 스텁·SQL)이 이 규칙을 공유한다. 각자 거르면 스텁으로
통과한 테스트가 실제 DB에서 다르게 동작한다.

점수는 0~1로 맞춘다 — 어휘 검색은 겹침 비율, 벡터 검색은 코사인 유사도다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from backend.services.knowledge.base import DiaryLookup, DiaryReference

# 한 글자 토큰은 조사·감탄사가 대부분이라 아무 일기에나 걸린다.
_MIN_TOKEN_LEN = 2


@dataclass(frozen=True)
class DiaryThresholds:
    # 절대 바닥. 이 미만 후보는 버린다.
    min_score: float = 0.5
    # 최소 이만큼의 의미 토큰이 겹쳐야 후보로 인정한다(본문 포함).
    min_match_tokens: int = 1
    # 요약·제목에 최소 이만큼 겹쳐야 한다. 본문에만 걸린 건 근거로 약하다.
    min_headline_tokens: int = 1
    # 남은 것 중 최상위가 이 값에 못 미치면 그 턴은 아예 참조하지 않는다.
    strong_score: float = 0.7

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "DiaryThresholds":
        counsel = (config or {}).get("counsel") or {}
        defaults = cls()
        return cls(
            min_score=float(counsel.get("diary_min_score", defaults.min_score)),
            min_match_tokens=int(
                counsel.get("diary_min_match_tokens", defaults.min_match_tokens)
            ),
            min_headline_tokens=int(
                counsel.get("diary_min_headline_tokens", defaults.min_headline_tokens)
            ),
            strong_score=float(counsel.get("diary_strong_score", defaults.strong_score)),
        )


@dataclass(frozen=True)
class Candidate:
    """점수를 매긴 일기 하나. `select`가 이걸 보고 거른다.

    `matched`와 `headline_matched`를 나눠 두는 건 본문 매치와 요약 매치가
    다른 무게를 갖기 때문이다. `DiaryThresholds` 참고.
    """

    reference: DiaryReference
    matched: int  # 본문까지 포함해 겹친 토픽 토큰 수
    headline_matched: int  # 그중 제목·요약·감정태그에 걸린 수


def tokenize(*texts: str | None) -> list[str]:
    """질의에서 점수 계산에 쓸 토큰을 뽑는다.

    중복은 없앤다. 같은 낱말이 두 번 들어오면 분모만 커져서 점수가 낮아진다.
    """
    tokens: list[str] = []
    for text in texts:
        if not text:
            continue
        tokens.extend(
            token for token in text.split() if len(token.strip()) >= _MIN_TOKEN_LEN
        )
    return list(dict.fromkeys(token.strip() for token in tokens))


def score(
    tokens: Sequence[str],
    haystack: str,
    *,
    bonus_tokens: Sequence[str] = (),
) -> tuple[float, int]:
    """(겹침 비율, 겹친 토픽 토큰 수)를 돌려준다. """
    if not tokens:
        return 0.0, 0
    matched = sum(1 for token in tokens if token in haystack)
    bonus = sum(1 for token in bonus_tokens if token in haystack)
    return min((matched + bonus) / len(tokens), 1.0), matched


def select(
    candidates: Iterable[Candidate],
    thresholds: DiaryThresholds,
    *,
    max_items: int,
) -> list[DiaryReference]:
    """임계값을 통과한 일기만 관련도 순으로 돌려준다.

    최상위가 약하면 **전부** 버린다. 하나만 남겨 두면 "어쨌든 뭐라도 넣자"가
    되어, 지금 이야기와 상관없는 일기를 상담사가 억지로 꺼내게 된다.
    """
    kept = [
        candidate.reference
        for candidate in candidates
        if candidate.reference.score >= thresholds.min_score
        and candidate.matched >= thresholds.min_match_tokens
        and candidate.headline_matched >= thresholds.min_headline_tokens
    ]
    if not kept:
        return []

    kept.sort(key=lambda reference: reference.score, reverse=True)
    kept = kept[: max(max_items, 0)]
    if not kept or kept[0].score < thresholds.strong_score:
        return []
    return kept


def lookup(
    candidates: Iterable[Candidate],
    thresholds: DiaryThresholds,
    *,
    max_items: int,
) -> DiaryLookup:
    """`select`의 결과에 걸러지기 전 최고점을 붙여 돌려준다.

    검색 구현이 공통으로 부른다. 최고점을 각자 계산하게 두면 스텁과 SQL이
    서로 다른 값을 관측에 남기고, 그 숫자로 임계값을 옮기게 된다.

    후보를 한 번만 순회하도록 리스트로 굳힌다 — 제너레이터가 오면 `select`가
    소진해 최고점이 항상 None이 된다.
    """
    materialized = list(candidates)
    return DiaryLookup(
        references=select(materialized, thresholds, max_items=max_items),
        top_candidate_score=max(
            (candidate.reference.score for candidate in materialized), default=None
        ),
    )
