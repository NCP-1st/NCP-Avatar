"""벡터 검색용 임계값.

어휘 겹침(`DiaryThresholds`)과 숫자를 공유할 수 없다. 코사인 유사도는 분포가
전혀 달라서, 아무 상관 없는 두 문장도 0.3대가 흔히 나온다. 어휘 겹침의
0.5를 그대로 쓰면 무관한 일기가 통과한다.

거르는 **규칙** 자체는 `relevance.select`를 그대로 쓴다. 갈래마다 따로 거르면
한쪽을 고칠 때 다른 쪽이 조용히 달라진다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.services.knowledge.relevance import DiaryThresholds


@dataclass(frozen=True)
class VectorThresholds:
    """벡터 검색이 일기를 프롬프트에 넣을지 정하는 노브 2개."""

    # 절대 바닥. 이 미만 후보는 버린다.
    min_score: float = 0.52
    strong_score: float = 0.52
    # `backend/config.py`가 env 로 이 값을 덮어쓴다(DIARY_VEC_*). 기본값이
    # 양쪽에 있으므로 옮길 때 같이 옮긴다.

    def as_diary_thresholds(self) -> DiaryThresholds:
        """`relevance.select`가 이해하는 형태로 바꾼다.

        토큰 개수 게이트(`min_match_tokens`·`min_headline_tokens`)는 0으로
        연다. 벡터에는 "몇 낱말이 겹쳤나", "요약에 걸렸나"라는 개념이 아예
        없다. 0이 아닌 값을 넣으면 뜻 없는 조건으로 전부 탈락한다.
        """
        return DiaryThresholds(
            min_score=self.min_score,
            min_match_tokens=0,
            min_headline_tokens=0,
            strong_score=self.strong_score,
        )

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "VectorThresholds":
        counsel = (config or {}).get("counsel") or {}
        defaults = cls()
        return cls(
            min_score=float(counsel.get("diary_vec_min_score", defaults.min_score)),
            strong_score=float(
                counsel.get("diary_vec_strong_score", defaults.strong_score)
            ),
        )
